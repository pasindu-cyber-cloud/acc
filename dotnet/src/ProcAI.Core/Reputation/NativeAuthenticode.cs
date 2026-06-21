using System.Runtime.InteropServices;
using System.Security.Cryptography.X509Certificates;

namespace ProcAI.Core.Reputation;

/// <summary>
/// Read-only Authenticode verification via WinVerifyTrust. Returns whether a file
/// carries a valid signature and, if so, the signer's common name. This is a
/// reputation *signal* only — unsigned does not mean malicious.
/// </summary>
internal static class NativeAuthenticode
{
    private static readonly Guid WINTRUST_ACTION_GENERIC_VERIFY_V2 =
        new("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");

    private const uint WTD_UI_NONE = 2;
    private const uint WTD_REVOKE_NONE = 0;
    private const uint WTD_CHOICE_FILE = 1;
    private const uint WTD_STATEACTION_VERIFY = 1;
    private const uint WTD_STATEACTION_CLOSE = 2;

    [StructLayout(LayoutKind.Sequential)]
    private struct WINTRUST_FILE_INFO
    {
        public uint cbStruct;
        [MarshalAs(UnmanagedType.LPWStr)] public string pcwszFilePath;
        public IntPtr hFile;
        public IntPtr pgKnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WINTRUST_DATA
    {
        public uint cbStruct;
        public IntPtr pPolicyCallbackData;
        public IntPtr pSIPClientData;
        public uint dwUIChoice;
        public uint fdwRevocationChecks;
        public uint dwUnionChoice;
        public IntPtr pFile;
        public uint dwStateAction;
        public IntPtr hWVTStateData;
        public IntPtr pwszURLReference;
        public uint dwProvFlags;
        public uint dwUIContext;
    }

    [DllImport("wintrust.dll", ExactSpelling = true, CharSet = CharSet.Unicode, SetLastError = false)]
    private static extern uint WinVerifyTrust(IntPtr hwnd, [MarshalAs(UnmanagedType.LPStruct)] Guid pgActionID, IntPtr pWVTData);

    /// <summary>Return (isValidlySigned, signerCommonName). isSigned is null on error.</summary>
    public static (bool? IsSigned, string Signer) Verify(string filePath)
    {
        if (string.IsNullOrEmpty(filePath) || !File.Exists(filePath))
            return (null, string.Empty);

        bool? signed;
        try
        {
            signed = VerifyTrust(filePath) == 0;
        }
        catch
        {
            return (null, string.Empty);
        }

        string signer = string.Empty;
        try
        {
            using var cert = new X509Certificate2(X509Certificate.CreateFromSignedFile(filePath));
            signer = ExtractCommonName(cert.Subject);
        }
        catch
        {
            // Unsigned or signer not extractable; leave signer empty.
        }
        return (signed, signer);
    }

    private static uint VerifyTrust(string filePath)
    {
        var fileInfo = new WINTRUST_FILE_INFO
        {
            cbStruct = (uint)Marshal.SizeOf<WINTRUST_FILE_INFO>(),
            pcwszFilePath = filePath,
            hFile = IntPtr.Zero,
            pgKnownSubject = IntPtr.Zero,
        };

        IntPtr pFile = Marshal.AllocHGlobal(Marshal.SizeOf<WINTRUST_FILE_INFO>());
        IntPtr pData = IntPtr.Zero;
        try
        {
            Marshal.StructureToPtr(fileInfo, pFile, false);

            var data = new WINTRUST_DATA
            {
                cbStruct = (uint)Marshal.SizeOf<WINTRUST_DATA>(),
                dwUIChoice = WTD_UI_NONE,
                fdwRevocationChecks = WTD_REVOKE_NONE,
                dwUnionChoice = WTD_CHOICE_FILE,
                pFile = pFile,
                dwStateAction = WTD_STATEACTION_VERIFY,
            };

            pData = Marshal.AllocHGlobal(Marshal.SizeOf<WINTRUST_DATA>());
            Marshal.StructureToPtr(data, pData, false);

            uint result = WinVerifyTrust(IntPtr.Zero, WINTRUST_ACTION_GENERIC_VERIFY_V2, pData);

            // Always close the state data to release resources.
            data = Marshal.PtrToStructure<WINTRUST_DATA>(pData);
            data.dwStateAction = WTD_STATEACTION_CLOSE;
            Marshal.StructureToPtr(data, pData, false);
            WinVerifyTrust(IntPtr.Zero, WINTRUST_ACTION_GENERIC_VERIFY_V2, pData);

            return result;
        }
        finally
        {
            if (pData != IntPtr.Zero) Marshal.FreeHGlobal(pData);
            Marshal.FreeHGlobal(pFile);
        }
    }

    private static string ExtractCommonName(string subject)
    {
        foreach (var part in subject.Split(','))
        {
            var p = part.Trim();
            if (p.StartsWith("CN=", StringComparison.OrdinalIgnoreCase))
                return p[3..];
        }
        return subject;
    }
}
