using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using static Insectoids.EditorTools.InsectSetupUtil;
using Object = UnityEngine.Object;

namespace Insectoids.EditorTools
{
    /// <summary>
    /// Builds the spiderling (the giant spider's juvenile, a third of its size) from the files exported by Blender:
    ///   Spiderling.fbx              Generic rig (the spider's 58 bones), Motion = root-motion node, sockets kept
    ///   Anims/Spiderling@*.fbx      Idle, Walk / Run (root motion), Hit, Death, GetUp, Bite at 60 fps; events OnInsectEvent
    ///                               (Bite, Dead) from Anims/spiderling_clips.json
    ///   Materials                   M_Spiderling (+ Amber, Dusky skins; smoothness from the texture's alpha)
    ///   Prefabs/Spider_Spiderling   Animator + InsectAppearance (skin, size) + InsectEvents
    ///   Animation/SpiderlingAnims   clip pools for InsectRandomAnimator
    /// then the shared test scene. Tools > Insectoids > Rebuild Spiderling (runs by itself the first time); report and
    /// renders in Logs/SpiderlingSetup.
    /// </summary>
    [InitializeOnLoad]
    public static class SpiderlingSetup
    {
        const string ModelPath = Models + "/Spiderling.fbx";
        public const string PrefabPath = Prefabs + "/Spider_Spiderling.prefab";
        public const string SetPath = SetDir + "/SpiderlingAnims.asset";

        static PoolDef[] Pools() => new[]
        {
            new PoolDef("Idle", 2f, "Idle") { h0 = 1.5f, h1 = 3 },
            new PoolDef("Walk", 2.2f, "Walk") { moves = true, h0 = 2, h1 = 4 },
            new PoolDef("Run", 1.4f, "Run") { moves = true, h0 = 1, h1 = 2.5f },
            new PoolDef("Bite", 1.2f, "Bite") { next = "Idle" },
            new PoolDef("Hit", 0.6f, "Hit") { next = "Idle" },
            new PoolDef("Death", 0.25f, "Death") { after = 2.5f, next = "GetUp" },
            new PoolDef("GetUp", 0f, "GetUp") { next = "Idle" },                       // from the slumped Death (2026-10-23)
        };

        static SpiderlingSetup() => EditorApplication.delayCall += () => AutoBuild(30);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(ModelPath) || File.Exists(PrefabPath)) return;
            bool ready = AssetImporter.GetAtPath(ModelPath) is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Spiderling.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        [MenuItem("Tools/Insectoids/Rebuild Spiderling")]
        public static void Build() => Run(true);

        public static void Run(bool scenes)
        {
            var dir = OutDir("SpiderlingSetup");
            Directory.CreateDirectory(dir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                EnsureFolders();
                ConfigureSmoothnessTexture(Textures + "/T_Spiderling.png");
                var basic = MakeLit("M_Spiderling", Textures + "/T_Spiderling.png", Color.white);
                var amber = MakeLit("M_Spiderling_Amber", Textures + "/T_Spiderling.png", new Color(1f, 0.88f, 0.72f));
                var dusky = MakeLit("M_Spiderling_Dusky", Textures + "/T_Spiderling.png", new Color(0.8f, 0.78f, 0.76f));

                var (avatar, motionPath, model) = ConfigureModel(ModelPath, new[] { ("M_Spiderling", basic) }, log);
                var clips = ConfigureClips("Spiderling", Anims + "/spiderling_clips.json", avatar, motionPath, EventFunction, log);
                MakeSet("SpiderlingAnims", Pools(), clips, log);

                var go = NewCreature(model, avatar, "Spider_Spiderling");
                var look = go.GetComponent<InsectAppearance>() ?? go.AddComponent<InsectAppearance>();
                look.skins = new[] { basic, basic, amber, dusky };
                look.materialSlot = 0;
                look.scale = new Vector2(0.85f, 1.15f);
                if (go.GetComponent<InsectEvents>() == null) go.AddComponent<InsectEvents>();
                var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
                Object.DestroyImmediate(go);
                log.AppendLine("  prefab: " + PrefabPath);

                if (scenes)
                {
                    InsectoidsTestScene.Build(log);
                    InsectoidsTestScene.RenderLineup(prefab, clips, new (string, float)[]
                    {
                        ("Idle", 1f), ("Walk", 0.1f), ("Run", 0.1f), ("Bite", 0.35f), ("Hit", 0.12f), ("Death", 1.6f),
                    }, dir, 1.3f, 0.2f, log);
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
                Debug.Log("Spiderling setup finished: " + Path.Combine(dir, "setup_report.txt"));
            }
        }
    }
}
