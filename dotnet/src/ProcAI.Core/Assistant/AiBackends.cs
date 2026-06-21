using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using ProcAI.Core.Configuration;
using ProcAI.Core.Utils;

namespace ProcAI.Core.Assistant;

/// <summary>Raised when an AI backend cannot be used (disabled, privacy, or unreachable).</summary>
public sealed class AiUnavailableException : Exception
{
    public AiUnavailableException(string message) : base(message) { }
}

/// <summary>Describes what the assistant can currently do, for the GUI.</summary>
public sealed record AiBackendStatus(
    bool OfflineAlwaysAvailable, bool AssistantEnabled, bool PrivacyFirst,
    string SelectedBackend, bool CloudAllowed);

/// <summary>
/// Optional AI chat backends for the Proc Assistant (privacy-gated).
///   * Ollama  -> a LOCAL LLM server; data stays on the machine (preferred).
///   * Gemini  -> Google's hosted API; only allowed when the user has explicitly
///                enabled the assistant AND disabled privacy-first mode.
/// The offline <see cref="Explainer"/> is always the default and never sends data.
/// </summary>
public static class AiBackends
{
    private const string SystemPreamble =
        "You are Proc Assistant, a careful, defensive cybersecurity helper inside the ProcAI " +
        "endpoint-security tool. Explain process behaviour in clear, plain language. Be cautious " +
        "and never tell the user to disable security software. Recommend safe, reversible " +
        "investigation steps. If evidence is weak, say so.";

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(60) };

    public static AiBackendStatus Status(Settings s) => new(
        OfflineAlwaysAvailable: true,
        AssistantEnabled: s.AiAssistantEnabled,
        PrivacyFirst: s.PrivacyFirstMode,
        SelectedBackend: s.AiBackend,
        CloudAllowed: s.AiAssistantEnabled && !s.PrivacyFirstMode);

    public static async Task<string> AskAsync(Settings s, string prompt, string context = "", AuditLog? audit = null)
    {
        string full = ComposePrompt(prompt, context);
        switch (s.AiBackend)
        {
            case "ollama":
                Guard(s, cloud: false);
                audit?.Record("assistant.query", new { backend = "ollama", local = true });
                return await AskOllamaAsync(s, full);
            case "gemini":
                Guard(s, cloud: true);
                audit?.Record("assistant.query", new { backend = "gemini", local = false });
                return await AskGeminiAsync(s, full);
            default:
                throw new AiUnavailableException(
                    "No cloud/local AI backend selected. The offline explainer is being used instead.");
        }
    }

    private static void Guard(Settings s, bool cloud)
    {
        if (!s.AiAssistantEnabled)
            throw new AiUnavailableException("AI assistant is disabled. Enable it in Settings to use chat mode.");
        if (cloud && s.PrivacyFirstMode)
            throw new AiUnavailableException(
                "Privacy-first mode blocks cloud AI. Use the local Ollama backend or disable privacy-first mode explicitly.");
    }

    private static string ComposePrompt(string question, string context)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine(SystemPreamble);
        if (!string.IsNullOrEmpty(context))
            sb.AppendLine("\n--- Detection context (from ProcAI, on this machine) ---\n" + context);
        sb.AppendLine("\n--- User question ---\n" + question);
        return sb.ToString();
    }

    private static async Task<string> AskOllamaAsync(Settings s, string prompt)
    {
        try
        {
            var url = s.AiOllamaHost.TrimEnd('/') + "/api/generate";
            var resp = await Http.PostAsJsonAsync(url, new { model = s.AiOllamaModel, prompt, stream = false });
            resp.EnsureSuccessStatusCode();
            using var doc = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
            return doc.RootElement.TryGetProperty("response", out var r) ? (r.GetString() ?? "(empty response)") : "(empty response)";
        }
        catch (Exception ex)
        {
            throw new AiUnavailableException($"Could not reach local Ollama at {s.AiOllamaHost}: {ex.Message}");
        }
    }

    private static async Task<string> AskGeminiAsync(Settings s, string prompt)
    {
        if (string.IsNullOrEmpty(s.AiGeminiApiKey))
            throw new AiUnavailableException("No Gemini API key set in Settings.");
        try
        {
            const string model = "gemini-1.5-flash";
            var url = $"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={s.AiGeminiApiKey}";
            var body = new { contents = new[] { new { parts = new[] { new { text = prompt } } } } };
            var resp = await Http.PostAsJsonAsync(url, body);
            resp.EnsureSuccessStatusCode();
            using var doc = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
            var text = doc.RootElement
                .GetProperty("candidates")[0].GetProperty("content").GetProperty("parts")[0].GetProperty("text").GetString();
            return string.IsNullOrEmpty(text) ? "(empty response)" : text;
        }
        catch (AiUnavailableException) { throw; }
        catch (Exception ex)
        {
            throw new AiUnavailableException($"Gemini request failed: {ex.Message}");
        }
    }
}
