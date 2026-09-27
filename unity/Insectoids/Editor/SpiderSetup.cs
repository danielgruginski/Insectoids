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
    /// Builds the giant spider from the files exported by Blender (Assets/Insectoids/Models, Textures):
    ///   Spider.fbx            Generic rig, avatar from this model, Motion = root-motion node, sockets kept
    ///   Anims/Spider@*.fbx    one clip each, avatar copied from Spider.fbx; loop flags, root motion and animation
    ///                         events (OnInsectEvent: Bite, Strike, Spit, Dead) from Anims/spider_clips.json
    ///   Materials             M_Spider (+ Rust, Dark, Pale skins), smoothness from the texture's alpha;
    ///                         M_Spider_Web / _Silk / _SilkThread for the web spit
    ///   Prefabs/Spider_Giant  Animator + SpiderAppearance (skin, size) + SpiderCombat (events, web spit)
    ///   Animation/SpiderAnims clip pools for InsectRandomAnimator
    /// then the shared test scene (InsectoidsTestScene). Runs once by itself the first time the files are imported;
    /// afterwards Tools > Insectoids > Rebuild Spider. A report and renders go to Logs/SpiderSetup.
    /// </summary>
    [InitializeOnLoad]
    public static class SpiderSetup
    {
        const string ModelPath = Models + "/Spider.fbx";
        public const string PrefabPath = Prefabs + "/Spider_Giant.prefab";
        public const string SetPath = SetDir + "/SpiderAnims.asset";

        static PoolDef[] Pools() => new[]
        {
            new PoolDef("Idle", 2f, "Idle") { h0 = 2, h1 = 4 },
            new PoolDef("Walk", 2.4f, "Walk") { moves = true, h0 = 3, h1 = 6 },
            new PoolDef("Run", 0.8f, "Run") { moves = true, h0 = 1.5f, h1 = 3 },
            new PoolDef("Threat", 0.9f, "Threat") { next = "Idle" },
            new PoolDef("Bite", 1.4f, "Bite") { next = "Idle" },
            new PoolDef("Strike", 1f, "Strike") { next = "Idle" },
            new PoolDef("WebSpit", 1.2f, "WebSpit") { next = "Idle" },
            new PoolDef("Hit", 0.6f, "Hit") { next = "Idle" },
            new PoolDef("Death", 0.3f, "Death") { after = 2f, next = "GetUp" },
            new PoolDef("GetUp", 0f, "GetUp") { next = "Idle" },
        };

        static SpiderSetup() => EditorApplication.delayCall += () => AutoBuild(20);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(ModelPath) || File.Exists(PrefabPath)) return;
            bool ready = AssetImporter.GetAtPath(ModelPath) is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Spider.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        [MenuItem("Tools/Insectoids/Rebuild Spider")]
        public static void Build() => Run(true);

        /// <summary>scenes: also rebuild the shared test scene and the renders.</summary>
        public static void Run(bool scenes)
        {
            var dir = OutDir("SpiderSetup");
            Directory.CreateDirectory(dir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                EnsureFolders();
                foreach (var t in new[] { "T_Spider", "T_Spider_Pale" }) ConfigureSmoothnessTexture($"{Textures}/{t}.png");
                var hunter = MakeLit("M_Spider", Textures + "/T_Spider.png", Color.white);
                var pale = MakeLit("M_Spider_Pale", Textures + "/T_Spider_Pale.png", Color.white);
                var rust = MakeLit("M_Spider_Rust", Textures + "/T_Spider.png", new Color(1f, 0.8f, 0.68f));
                var dark = MakeLit("M_Spider_Dark", Textures + "/T_Spider.png", new Color(0.72f, 0.72f, 0.74f));
                var (web, silk, thread) = MakeWebMaterials();

                var (avatar, motionPath, model) = ConfigureModel(ModelPath, new[] { ("M_Spider", hunter) }, log);
                var clips = ConfigureClips("Spider", Anims + "/spider_clips.json", avatar, motionPath, EventFunction, log);
                var set = MakeSet("SpiderAnims", Pools(), clips, log);

                var go = NewCreature(model, avatar, "Spider_Giant");
                var look = go.GetComponent<SpiderAppearance>() ?? go.AddComponent<SpiderAppearance>();
                look.skins = new[] { hunter, hunter, hunter, rust, dark, pale };     // listed twice = twice as likely
                look.scale = new Vector2(0.85f, 1.2f);
                var combat = go.GetComponent<SpiderCombat>() ?? go.AddComponent<SpiderCombat>();
                combat.webMaterial = web;
                combat.silkMaterial = silk;
                combat.threadMaterial = thread;
                var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
                Object.DestroyImmediate(go);
                log.AppendLine("  prefab: " + PrefabPath);

                if (scenes)
                {
                    InsectoidsTestScene.Build(log);
                    InsectoidsTestScene.RenderLineup(prefab, clips, new (string, float)[]
                    {
                        ("Idle", 1f), ("Walk", 0.25f), ("Threat", 1.1f), ("Bite", 0.5f), ("Strike", 0.6f), ("WebSpit", 0.67f), ("Death", 2f),
                    }, dir, 3.6f, 0.5f, log);
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
                Debug.Log("Spider setup finished: " + Path.Combine(dir, "setup_report.txt"));
            }
        }

        static (Material web, Material silk, Material thread) MakeWebMaterials()
        {
            var texPath = Textures + "/T_Spider_Web.png";
            if (!File.Exists(texPath))
            {
                File.WriteAllBytes(texPath, SpiderFx.WebTexture().EncodeToPNG());
                AssetDatabase.ImportAsset(texPath, ImportAssetOptions.ForceSynchronousImport);
            }
            var ti = (TextureImporter)AssetImporter.GetAtPath(texPath);
            ti.alphaIsTransparency = true;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.mipmapEnabled = true;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            ti.SaveAndReimport();
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            return (SaveMaterial(SpiderFx.AlphaMaterial(tex, "M_Spider_Web")), SaveMaterial(SpiderFx.SilkMaterial("M_Spider_Silk")),
                    SaveMaterial(SpiderFx.AlphaMaterial(null, "M_Spider_SilkThread")));
        }
    }
}
