using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using static Insectoids.EditorTools.InsectSetupUtil;
using Object = UnityEngine.Object;

namespace Insectoids.EditorTools
{
    /// <summary>
    /// Builds the spider-egg props (static, no rig) from the files exported by Blender:
    ///   SpiderEgg_Clutch.fbx / _Single.fbx / _Hatched.fbx   origin on the ground under the middle, one material
    ///   Materials        M_SpiderEggs (T_SpiderEggs, smoothness from the texture's alpha)
    ///   Prefabs          SpiderEgg_Clutch, SpiderEgg_Single (the broodmother's Spawn puts this one down),
    ///                    SpiderEgg_Hatched
    /// Tools > Insectoids > Rebuild Spider Eggs (runs by itself the first time); report and renders in
    /// Logs/SpiderEggsSetup, including the family at the game camera (eggs, spiderling, spider, broodmother).
    /// </summary>
    [InitializeOnLoad]
    public static class SpiderEggsSetup
    {
        public static readonly string[] Names = { "SpiderEgg_Clutch", "SpiderEgg_Single", "SpiderEgg_Hatched" };
        public static string PrefabPath(string name) => $"{Prefabs}/{name}.prefab";
        public static string SinglePath => PrefabPath("SpiderEgg_Single");

        static SpiderEggsSetup() => EditorApplication.delayCall += () => AutoBuild(30);

        static void AutoBuild(int retries)
        {
            if (!File.Exists($"{Models}/{Names[0]}.fbx") || File.Exists(PrefabPath(Names[0]))) return;
            bool ready = AssetImporter.GetAtPath($"{Models}/{Names[0]}.fbx") is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_SpiderEggs.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        [MenuItem("Tools/Insectoids/Rebuild Spider Eggs")]
        public static void Build() => Run(true);

        /// <summary>The prefabs only (the broodmother's setup calls this when her egg is missing).</summary>
        public static void MakePrefabs(StringBuilder log)
        {
            EnsureFolders();
            ConfigureSmoothnessTexture(Textures + "/T_SpiderEggs.png");
            var mat = MakeLit("M_SpiderEggs", Textures + "/T_SpiderEggs.png", Color.white);
            foreach (var name in Names)
            {
                var path = $"{Models}/{name}.fbx";
                if (!File.Exists(path))
                {
                    log.AppendLine("  missing " + path);
                    continue;
                }
                var model = ConfigureStaticModel(path, new[] { ("M_SpiderEggs", mat) }, log);
                var go = (GameObject)PrefabUtility.InstantiatePrefab(model);
                go.name = name;
                PrefabUtility.SaveAsPrefabAsset(go, PrefabPath(name));
                Object.DestroyImmediate(go);
                log.AppendLine("  prefab: " + PrefabPath(name));
            }
        }

        public static void Run(bool scenes)
        {
            var dir = OutDir("SpiderEggsSetup");
            Directory.CreateDirectory(dir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                MakePrefabs(log);
                if (scenes)
                {
                    InsectoidsTestScene.Build(log);
                    InsectoidsTestScene.RenderFamily(dir, log);
                }
                AssetDatabase.SaveAssets();
                log.AppendLine("OK");
            }
            catch (Exception e)
            {
                log.AppendLine("EXCEPTION " + e);
            }
            finally
            {
                Application.logMessageReceived -= onLog;
                File.WriteAllText(Path.Combine(dir, "setup_report.txt"), log.ToString());
                Debug.Log("Spider eggs setup finished: " + Path.Combine(dir, "setup_report.txt"));
            }
        }
    }
}
