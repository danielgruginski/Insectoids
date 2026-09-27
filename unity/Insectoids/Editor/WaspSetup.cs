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
    /// Builds the giant wasp from the files exported by Blender:
    ///   Wasp.fbx              Generic rig, Motion = root-motion node, two materials (shells, wings), sockets kept
    ///   Anims/Wasp@*.fbx      Idle (hover), Fly (root motion), Threat, Sting, Dive, Hit, Death, GetUp; events
    ///                         OnInsectEvent (Sting, Dead) from Anims/wasp_clips.json
    ///   Materials             M_Wasp (+ Hornet, Dark skins; smoothness from the texture's alpha), M_Wasp_Wing
    ///                         (transparent, both faces)
    ///   Prefabs/Wasp_Giant    Animator + InsectAppearance (skin, size) + InsectEvents
    ///   Animation/WaspAnims   clip pools for InsectRandomAnimator
    /// then the shared test scene. Tools > Insectoids > Rebuild Wasp (runs by itself the first time); report and
    /// renders in Logs/WaspSetup.
    /// </summary>
    [InitializeOnLoad]
    public static class WaspSetup
    {
        const string ModelPath = Models + "/Wasp.fbx";
        public const string PrefabPath = Prefabs + "/Wasp_Giant.prefab";
        public const string SetPath = SetDir + "/WaspAnims.asset";

        static PoolDef[] Pools() => new[]
        {
            new PoolDef("Idle", 2f, "Idle") { h0 = 2, h1 = 4 },
            new PoolDef("Fly", 2.4f, "Fly") { moves = true, h0 = 3, h1 = 6 },
            new PoolDef("Threat", 0.8f, "Threat") { next = "Idle" },
            new PoolDef("Sting", 1.4f, "Sting") { next = "Idle" },
            new PoolDef("Dive", 1f, "Dive") { next = "Idle" },
            new PoolDef("Hit", 0.6f, "Hit") { next = "Idle" },
            new PoolDef("Death", 0.3f, "Death") { after = 2f, next = "GetUp" },
            new PoolDef("GetUp", 0f, "GetUp") { next = "Idle" },
        };

        static WaspSetup() => EditorApplication.delayCall += () => AutoBuild(24);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(ModelPath) || File.Exists(PrefabPath)) return;
            bool ready = AssetImporter.GetAtPath(ModelPath) is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Wasp.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        [MenuItem("Tools/Insectoids/Rebuild Wasp")]
        public static void Build() => Run(true);

        public static void Run(bool scenes)
        {
            var dir = OutDir("WaspSetup");
            Directory.CreateDirectory(dir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                EnsureFolders();
                ConfigureSmoothnessTexture(Textures + "/T_Wasp.png");
                var wasp = MakeLit("M_Wasp", Textures + "/T_Wasp.png", Color.white);
                var hornet = MakeLit("M_Wasp_Hornet", Textures + "/T_Wasp.png", new Color(1f, 0.78f, 0.62f));
                var dark = MakeLit("M_Wasp_Dark", Textures + "/T_Wasp.png", new Color(0.74f, 0.72f, 0.7f));
                var wing = MakeTransparentLit("M_Wasp_Wing", Textures + "/T_Wasp_Wing.png", Color.white, 0.8f);

                var (avatar, motionPath, model) = ConfigureModel(ModelPath, new[] { ("M_Wasp", wasp), ("M_Wasp_Wing", wing) }, log);
                var clips = ConfigureClips("Wasp", Anims + "/wasp_clips.json", avatar, motionPath, EventFunction, log);
                var set = MakeSet("WaspAnims", Pools(), clips, log);

                var go = NewCreature(model, avatar, "Wasp_Giant");
                var look = go.GetComponent<InsectAppearance>() ?? go.AddComponent<InsectAppearance>();
                look.skins = new[] { wasp, wasp, wasp, hornet, dark };
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
                        ("Idle", 0.5f), ("Fly", 0.3f), ("Threat", 0.6f), ("Sting", 0.6f), ("Dive", 0.9f), ("Death", 2f),
                    }, dir, 3.0f, 1.2f, log);
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
                Debug.Log("Wasp setup finished: " + Path.Combine(dir, "setup_report.txt"));
            }
        }
    }
}
