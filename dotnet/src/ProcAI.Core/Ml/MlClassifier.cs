using System.Text.Json;
using Microsoft.ML;
using Microsoft.ML.Trainers.FastTree;
using ProcAI.Core.Configuration;
using ProcAI.Core.Detection;
using ProcAI.Core.Models;

namespace ProcAI.Core.Ml;

/// <summary>
/// ML.NET classifier wrapping one trained binary model plus its metadata.
/// Two interpretable algorithms are supported:
///   * "random_forest" -> FastForest (+ Platt calibration for probabilities)
///   * "decision_tree"  -> FastTree configured as a single shallow tree
/// Models persist to the per-user models directory as a .zip plus a metadata
/// sidecar (.json). All training and inference happen locally.
/// </summary>
public sealed class MlClassifier : IMlClassifier, IDisposable
{
    private static readonly HashSet<string> Algorithms = new() { "decision_tree", "random_forest" };

    private readonly MLContext _ml = new(seed: 42);
    private readonly AppPaths _paths;
    private readonly object _lock = new();

    private ITransformer? _model;
    private PredictionEngine<ProcessFeatures, ProcessPrediction>? _engine;
    private ModelMetadata? _metadata;

    public string Name { get; }
    public bool IsLoaded => _model is not null && _engine is not null;
    public ModelMetadata? Metadata => _metadata;

    public MlClassifier(string name = "random_forest", AppPaths? paths = null)
    {
        Name = Algorithms.Contains(name) ? name : "random_forest";
        _paths = paths ?? AppPaths.Default;
    }

    public string ModelPath => Path.Combine(_paths.ModelsDir, $"{Name}.zip");
    public string MetadataPath => Path.Combine(_paths.ModelsDir, $"{Name}.metadata.json");

    // ------------------------------------------------------------------ //

    public ModelMetadata Train(IReadOnlyList<(float[] Features, bool Label)> samples, double testFraction = 0.25)
    {
        if (samples.Count < 20)
            throw new ArgumentException("Need at least 20 labelled samples to train a model.");
        if (samples.All(s => s.Label) || samples.All(s => !s.Label))
            throw new ArgumentException("Training data must contain both normal and suspicious labels.");

        var rows = samples.Select(s => new ProcessFeatures { Features = s.Features, Label = s.Label });
        var data = _ml.Data.LoadFromEnumerable(rows);
        var split = _ml.Data.TrainTestSplit(data, testFraction: testFraction, seed: 42);

        IEstimator<ITransformer> pipeline;
        string algorithm;
        if (Name == "decision_tree")
        {
            algorithm = "FastTree (single decision tree)";
            pipeline = _ml.BinaryClassification.Trainers.FastTree(new FastTreeBinaryTrainer.Options
            {
                LabelColumnName = "Label",
                FeatureColumnName = "Features",
                NumberOfTrees = 1,
                NumberOfLeaves = 16,
                MinimumExampleCountPerLeaf = 5,
            });
        }
        else
        {
            algorithm = "FastForest (random forest)";
            var forest = _ml.BinaryClassification.Trainers.FastForest(new FastForestBinaryTrainer.Options
            {
                LabelColumnName = "Label",
                FeatureColumnName = "Features",
                NumberOfTrees = 200,
                NumberOfLeaves = 32,
                MinimumExampleCountPerLeaf = 3,
            });
            // FastForest is not calibrated by default; add Platt scaling for probabilities.
            pipeline = forest.Append(_ml.BinaryClassification.Calibrators.Platt(
                labelColumnName: "Label", scoreColumnName: "Score"));
        }

        var model = pipeline.Fit(split.TrainSet);
        var scored = model.Transform(split.TestSet);
        var metrics = _ml.BinaryClassification.Evaluate(scored, labelColumnName: "Label");

        var md = new ModelMetadata
        {
            Name = Name,
            Algorithm = algorithm,
            TrainedAt = ProcessSnapshot.UnixNow(),
            SampleCount = samples.Count,
            FeatureCount = FeatureExtractor.FeatureNames.Length,
            FeatureNames = FeatureExtractor.FeatureNames.ToList(),
            Accuracy = metrics.Accuracy,
            Precision = metrics.PositivePrecision,
            Recall = metrics.PositiveRecall,
            F1 = metrics.F1Score,
            Notes = $"Trained on {samples.Count} samples; test split {testFraction:P0}.",
        };

        lock (_lock)
        {
            _model = model;
            _metadata = md;
            _engine = _ml.Model.CreatePredictionEngine<ProcessFeatures, ProcessPrediction>(model);
            _trainSchema = data.Schema;
        }
        return md;
    }

    private Microsoft.ML.DataViewSchema? _trainSchema;

    public string Save()
    {
        lock (_lock)
        {
            if (_model is null || _trainSchema is null)
                throw new InvalidOperationException("No trained model to save.");
            _paths.Ensure();
            _ml.Model.Save(_model, _trainSchema, ModelPath);
            if (_metadata is not null)
                File.WriteAllText(MetadataPath,
                    JsonSerializer.Serialize(_metadata, new JsonSerializerOptions { WriteIndented = true }));
        }
        return ModelPath;
    }

    public bool Load()
    {
        try
        {
            if (!File.Exists(ModelPath)) return false;
            var model = _ml.Model.Load(ModelPath, out _);
            ModelMetadata? md = null;
            if (File.Exists(MetadataPath))
                md = JsonSerializer.Deserialize<ModelMetadata>(File.ReadAllText(MetadataPath));

            lock (_lock)
            {
                _model = model;
                _metadata = md;
                _engine = _ml.Model.CreatePredictionEngine<ProcessFeatures, ProcessPrediction>(model);
            }
            return true;
        }
        catch
        {
            return false;
        }
    }

    // ------------------------------------------------------------------ //

    public MlResult Predict(ProcessSnapshot snapshot)
    {
        if (!IsLoaded) return MlResult.Unavailable(Name);
        var input = new ProcessFeatures { Features = FeatureExtractor.ToVector(snapshot) };

        ProcessPrediction prediction;
        lock (_lock)
        {
            // PredictionEngine is not thread-safe; guard it.
            prediction = _engine!.Predict(input);
        }

        double p = double.IsNaN(prediction.Probability) ? (prediction.IsSuspicious ? 1.0 : 0.0) : prediction.Probability;
        p = Math.Clamp(p, 0.0, 1.0);

        return new MlResult
        {
            Available = true,
            ModelName = Name,
            IsSuspicious = p >= 0.5,
            Probability = p,
            Confidence = Math.Abs(p - 0.5) * 2.0,
            TopFeatures = Array.Empty<(string, double)>(),
        };
    }

    public void Dispose()
    {
        _engine?.Dispose();
    }

    /// <summary>Convenience: train the named algorithm and persist it.</summary>
    public static ModelMetadata TrainAndSave(string name, IReadOnlyList<(float[] Features, bool Label)> samples, AppPaths? paths = null)
    {
        var clf = new MlClassifier(name, paths);
        var md = clf.Train(samples);
        clf.Save();
        return md;
    }
}
