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
    /// Builds the giant centipede from the files exported by Blender:
    ///   Centipede.fbx            Generic rig (107 bones), Motion = root-motion node, sockets kept
    ///   Anims/Centipede@*.fbx    Idle, Walk / Run / Burrow / Emerge (root motion), Threat, Bite, Hit, Death, GetUp (60 fps);
    ///                            events OnInsectEvent (Bite, Burrow, Emerge, Dead) from Anims/centipede_clips.json
    ///   Materials                M_Centipede (+ Dark, Rust skins; smoothness from the texture's alpha),
    ///                            M_Centipede_Hole, M_Centipede_Dirt for the burrow
    ///   Prefabs/Centipede_Giant  Animator + InsectAppearance + InsectEvents + CentipedeBurrow
    ///   Animation/CentipedeAnims clip pools (Burrow, 3-8 m underground, then Emerge)
    /// then the shared test scene. Tools > Insectoids > Rebuild Centipede (runs by itself the first time); report and
    /// renders in Logs/CentipedeSetup.
    /// </summary>
    [InitializeOnLoad]
    public static class CentipedeSetup
    {
        const string ModelPath = Models + "/Centipede.fbx";
        public const string PrefabPath = Prefabs + "/Centipede_Giant.prefab";
        public const string SetPath = SetDir + "/CentipedeAnims.asset";

        static PoolDef[] Pools() => new[]
        {
            new PoolDef("Idle", 2f, "Idle") { h0 = 2, h1 = 4 },
            new PoolDef("Walk", 2.2f, "Walk") { moves = true, h0 = 3, h1 = 6 },
            new PoolDef("Run", 0.8f, "Run") { moves = true, h0 = 1.5f, h1 = 3 },
            new PoolDef("Threat", 0.8f, "Threat") { next = "Idle" },
            new PoolDef("Bite", 1.3f, "Bite") { next = "Idle" },
            new PoolDef("Burrow", 0.6f, "Burrow") { after = 1.5f, next = "Emerge", relocate = new Vector2(3f, 8f) },
            new PoolDef("Emerge", 0f, "Emerge") { next = "Idle" },
            new PoolDef("Hit", 0.5f, "Hit") { next = "Idle" },
            new PoolDef("Death", 0.3f, "Death") { after = 2f, next = "GetUp" },
            new PoolDef("GetUp", 0f, "GetUp") { next = "Idle" },
        };

        static CentipedeSetup() => EditorApplication.delayCall += () => AutoBuild(200);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(ModelPath) || File.Exists(PrefabPath)) return;
            bool ready = AssetImporter.GetAtPath(ModelPath) is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Centipede.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        [MenuItem("Tools/Insectoids/Rebuild Centipede")]
        public static void Build() => Run(true);

        public static void Run(bool scenes)
        {
            var dir = OutDir("CentipedeSetup");
            Directory.CreateDirectory(dir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                EnsureFolders();
                ConfigureSmoothnessTexture(Textures + "/T_Centipede.png");
                var basic = MakeLit("M_Centipede", Textures + "/T_Centipede.png", Color.white);
                var dark = MakeLit("M_Centipede_Dark", Textures + "/T_Centipede.png", new Color(0.72f, 0.7f, 0.72f));
                var rust = MakeLit("M_Centipede_Rust", Textures + "/T_Centipede.png", new Color(1f, 0.82f, 0.7f));
                var holeTexPath = Textures + "/T_Centipede_Hole.png";
                if (!File.Exists(holeTexPath))
                {
                    File.WriteAllBytes(holeTexPath, CentipedeBurrow.HoleTexture().EncodeToPNG());
                    AssetDatabase.ImportAsset(holeTexPath, ImportAssetOptions.ForceSynchronousImport);
                }
                var ti = (TextureImporter)AssetImporter.GetAtPath(holeTexPath);
                ti.alphaIsTransparency = true;
                ti.wrapMode = TextureWrapMode.Clamp;
                ti.SaveAndReimport();
                var hole = SaveMaterial(SpiderFx.AlphaMaterial(AssetDatabase.LoadAssetAtPath<Texture2D>(holeTexPath), "M_Centipede_Hole"));
                var dirtFresh = SpiderFx.SilkMaterial("M_Centipede_Dirt");
                var dc = new Color(0.36f, 0.28f, 0.19f);
                dirtFresh.color = dc;
                if (dirtFresh.HasProperty("_BaseColor")) dirtFresh.SetColor("_BaseColor", dc);
                if (dirtFresh.HasProperty("_Smoothness")) dirtFresh.SetFloat("_Smoothness", 0.05f);
                var dirt = SaveMaterial(dirtFresh);

                var (avatar, motionPath, model) = ConfigureModel(ModelPath, new[] { ("M_Centipede", basic) }, log);
                var clips = ConfigureClips("Centipede", Anims + "/centipede_clips.json", avatar, motionPath, EventFunction, log);
                var set = MakeSet("CentipedeAnims", Pools(), clips, log);

                var go = NewCreature(model, avatar, "Centipede_Giant");
                var look = go.GetComponent<InsectAppearance>() ?? go.AddComponent<InsectAppearance>();
                look.skins = new[] { basic, basic, basic, dark, rust };
                look.scale = new Vector2(0.85f, 1.2f);
                if (go.GetComponent<InsectEvents>() == null) go.AddComponent<InsectEvents>();
                var burrow = go.GetComponent<CentipedeBurrow>() ?? go.AddComponent<CentipedeBurrow>();
                burrow.holeMaterial = hole;
                burrow.dirtMaterial = dirt;
                var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
                Object.DestroyImmediate(go);
                log.AppendLine("  prefab: " + PrefabPath);

                if (scenes)
                {
                    InsectoidsTestScene.Build(log);
                    InsectoidsTestScene.RenderLineup(prefab, clips, new (string, float)[]
                    {
                        ("Idle", 1f), ("Walk", 0.3f), ("Threat", 1.2f), ("Bite", 0.55f), ("Burrow", 1.0f), ("Death", 2f),
                    }, dir, 2.6f, 0.4f, log);
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
                Debug.Log("Centipede setup finished: " + Path.Combine(dir, "setup_report.txt"));
            }
        }
    }
}
