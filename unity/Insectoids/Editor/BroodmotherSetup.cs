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
    /// Builds the broodmother (a bloated giant spider 1.8x the adult, egg sacs on her back) from the files exported by
    /// Blender:
    ///   Broodmother.fbx              Generic rig (the spider's bones + SpawnEgg, the egg she lays), Motion = root-motion
    ///                                node, sockets kept (Socket_Spinneret: where her eggs come down)
    ///   Anims/Broodmother@*.fbx      Idle, Walk (root motion), Threat, Bite, Spawn, Hit, Death, GetUp; events OnInsectEvent
    ///                                (Bite, Spawn, Dead) from Anims/broodmother_clips.json; Abdomen and SpawnEgg scale
    ///   Materials                    M_Broodmother (+ Ashen skin; smoothness from the texture's alpha)
    ///   Prefabs/Spider_Broodmother   Animator + InsectAppearance + InsectEvents + SpiderBrood (Spawn puts down
    ///                                SpiderEgg_Single under the spinnerets)
    ///   Animation/BroodmotherAnims   clip pools for InsectRandomAnimator
    /// then the shared test scene. Tools > Insectoids > Rebuild Broodmother (runs by itself the first time); report and
    /// renders in Logs/BroodmotherSetup.
    /// </summary>
    [InitializeOnLoad]
    public static class BroodmotherSetup
    {
        const string ModelPath = Models + "/Broodmother.fbx";
        public const string PrefabPath = Prefabs + "/Spider_Broodmother.prefab";
        public const string SetPath = SetDir + "/BroodmotherAnims.asset";

        static PoolDef[] Pools() => new[]
        {
            new PoolDef("Idle", 2f, "Idle") { h0 = 3, h1 = 6 },
            new PoolDef("Walk", 1.8f, "Walk") { moves = true, h0 = 3, h1 = 6 },
            new PoolDef("Threat", 0.8f, "Threat") { next = "Idle" },
            new PoolDef("Bite", 1f, "Bite") { next = "Idle" },
            new PoolDef("Spawn", 1f, "Spawn") { next = "Idle" },
            new PoolDef("Hit", 0.5f, "Hit") { next = "Idle" },
            new PoolDef("Death", 0.2f, "Death") { after = 3f, next = "GetUp" },
            new PoolDef("GetUp", 0f, "GetUp") { next = "Idle" },                        // from the slumped Death (2026-10-23)
        };

        static BroodmotherSetup() => EditorApplication.delayCall += () => AutoBuild(40);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(ModelPath) || File.Exists(PrefabPath)) return;
            bool ready = AssetImporter.GetAtPath(ModelPath) is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Broodmother.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        [MenuItem("Tools/Insectoids/Rebuild Broodmother")]
        public static void Build() => Run(true);

        public static void Run(bool scenes)
        {
            var dir = OutDir("BroodmotherSetup");
            Directory.CreateDirectory(dir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                EnsureFolders();
                ConfigureSmoothnessTexture(Textures + "/T_Broodmother.png");
                var basic = MakeLit("M_Broodmother", Textures + "/T_Broodmother.png", Color.white);
                var ashen = MakeLit("M_Broodmother_Ashen", Textures + "/T_Broodmother.png", new Color(0.86f, 0.84f, 0.82f));

                var (avatar, motionPath, model) = ConfigureModel(ModelPath, new[] { ("M_Broodmother", basic) }, log);
                var clips = ConfigureClips("Broodmother", Anims + "/broodmother_clips.json", avatar, motionPath, EventFunction, log);
                MakeSet("BroodmotherAnims", Pools(), clips, log);

                if (AssetDatabase.LoadAssetAtPath<GameObject>(SpiderEggsSetup.SinglePath) == null)
                    SpiderEggsSetup.MakePrefabs(log);
                var go = NewCreature(model, avatar, "Spider_Broodmother");
                var look = go.GetComponent<InsectAppearance>() ?? go.AddComponent<InsectAppearance>();
                look.skins = new[] { basic, basic, ashen };
                look.materialSlot = 0;
                look.scale = new Vector2(0.92f, 1.08f);
                if (go.GetComponent<InsectEvents>() == null) go.AddComponent<InsectEvents>();
                var brood = go.GetComponent<SpiderBrood>() ?? go.AddComponent<SpiderBrood>();
                brood.spawnPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(SpiderEggsSetup.SinglePath);
                log.AppendLine("  SpiderBrood spawns: " + (brood.spawnPrefab != null ? brood.spawnPrefab.name : "NOTHING (no egg prefab)"));
                var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
                Object.DestroyImmediate(go);
                log.AppendLine("  prefab: " + PrefabPath);

                if (scenes)
                {
                    InsectoidsTestScene.Build(log);
                    InsectoidsTestScene.RenderLineup(prefab, clips, new (string, float)[]
                    {
                        ("Idle", 1f), ("Walk", 0.4f), ("Threat", 1.2f), ("Bite", 0.62f), ("Spawn", 2.85f), ("Death", 2.6f),
                    }, dir, 6.5f, 1.0f, log);
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
                Debug.Log("Broodmother setup finished: " + Path.Combine(dir, "setup_report.txt"));
            }
        }
    }
}
