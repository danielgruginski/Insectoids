using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace Insectoids.EditorTools
{
    /// <summary>
    /// What the creature setups (SpiderSetup, WaspSetup) share: folders, materials, the Generic model import with the
    /// Motion bone as root-motion node, clip import from the exported JSON (loop, root motion, events), animation sets,
    /// and verification renders.
    /// </summary>
    public static class InsectSetupUtil
    {
        public const string Root = "Assets/Insectoids";
        public const string Models = Root + "/Models";
        public const string Anims = Models + "/Anims";
        public const string Textures = Root + "/Textures";
        public const string Materials = Root + "/Materials";
        public const string Prefabs = Root + "/Prefabs";
        public const string Scenes = Root + "/Scenes";
        public const string SetDir = Root + "/Animation";
        public const string EventFunction = "OnInsectEvent";

        public static string OutDir(string name) =>
            Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Logs", name));

        [Serializable] class ClipEvent { public string name; public float time; }
        [Serializable] class ClipInfo { public string name; public int frames; public int fps; public bool loop; public bool rootMotion; public ClipEvent[] events; }
        [Serializable] class ClipList { public ClipInfo[] clips; }

        public class PoolDef
        {
            public string name, next;
            public float w, h0 = 3, h1 = 6, after;
            public string[] clips;
            public bool moves;
            public Vector2 relocate;
            public PoolDef(string name, float w, params string[] clips) { this.name = name; this.w = w; this.clips = clips; }
        }

        public static void EnsureFolders()
        {
            foreach (var d in new[] { Materials, Prefabs, Scenes, SetDir }) EnsureFolder(d);
        }

        public static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            var parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        /// <summary>Painted colour texture whose alpha holds smoothness.</summary>
        public static void ConfigureSmoothnessTexture(string path)
        {
            if (!(AssetImporter.GetAtPath(path) is TextureImporter ti)) return;
            ti.maxTextureSize = 1024;
            ti.sRGBTexture = true;
            ti.mipmapEnabled = true;
            ti.alphaSource = TextureImporterAlphaSource.FromInput;     // alpha = smoothness, not transparency
            ti.alphaIsTransparency = false;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            ti.SaveAndReimport();
        }

        static Shader LitShader => GraphicsSettings.currentRenderPipeline != null
            ? GraphicsSettings.currentRenderPipeline.defaultShader : Shader.Find("Standard");

        static Material LoadOrCreate(string name)
        {
            var path = $"{Materials}/{name}.mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null)
            {
                mat = new Material(LitShader) { name = name };
                AssetDatabase.CreateAsset(mat, path);
            }
            mat.shader = LitShader;
            return mat;
        }

        /// <summary>URP Lit with the painted texture; smoothness from its alpha (glossy eyes, matte hair).</summary>
        public static Material MakeLit(string name, string texPath, Color tint)
        {
            var mat = LoadOrCreate(name);
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            mat.mainTexture = tex;
            if (mat.HasProperty("_BaseMap")) mat.SetTexture("_BaseMap", tex);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", tint);
            else mat.color = tint;
            if (mat.HasProperty("_SmoothnessTextureChannel"))
            {
                mat.SetFloat("_SmoothnessTextureChannel", 1f);
                mat.EnableKeyword("_SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A");
            }
            if (mat.HasProperty("_Smoothness")) mat.SetFloat("_Smoothness", 1f);
            if (mat.HasProperty("_Metallic")) mat.SetFloat("_Metallic", 0f);
            EditorUtility.SetDirty(mat);
            return mat;
        }

        /// <summary>URP Lit, transparent (alpha blended), both faces: insect wings.</summary>
        public static Material MakeTransparentLit(string name, string texPath, Color tint, float smoothness)
        {
            var ti = AssetImporter.GetAtPath(texPath) as TextureImporter;
            if (ti != null)
            {
                ti.alphaIsTransparency = true;
                ti.alphaSource = TextureImporterAlphaSource.FromInput;
                ti.sRGBTexture = true;
                ti.wrapMode = TextureWrapMode.Clamp;
                ti.textureCompression = TextureImporterCompression.CompressedHQ;
                ti.SaveAndReimport();
            }
            var mat = LoadOrCreate(name);
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            mat.mainTexture = tex;
            if (mat.HasProperty("_BaseMap")) mat.SetTexture("_BaseMap", tex);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", tint);
            mat.SetFloat("_Surface", 1f);                       // transparent
            mat.SetFloat("_Blend", 0f);                         // alpha
            mat.SetFloat("_Cull", 0f);                          // both faces
            mat.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            mat.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            mat.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            mat.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            mat.SetFloat("_ZWrite", 0f);
            mat.SetFloat("_AlphaClip", 0f);
            if (mat.HasProperty("_Smoothness")) mat.SetFloat("_Smoothness", smoothness);
            if (mat.HasProperty("_SmoothnessTextureChannel")) mat.SetFloat("_SmoothnessTextureChannel", 0f);
            mat.DisableKeyword("_SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A");
            mat.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            mat.DisableKeyword("_ALPHATEST_ON");
            mat.SetOverrideTag("RenderType", "Transparent");
            mat.renderQueue = (int)RenderQueue.Transparent;
            mat.SetShaderPassEnabled("ShadowCaster", false);
            EditorUtility.SetDirty(mat);
            return mat;
        }

        public static Material SaveMaterial(Material fresh)
        {
            var path = $"{Materials}/{fresh.name}.mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null)
            {
                AssetDatabase.CreateAsset(fresh, path);
                return fresh;
            }
            mat.shader = fresh.shader;
            mat.CopyPropertiesFromMaterial(fresh);
            mat.shaderKeywords = fresh.shaderKeywords;
            mat.renderQueue = fresh.renderQueue;
            if (fresh.GetTag("RenderType", false) == "Transparent") mat.SetOverrideTag("RenderType", "Transparent");
            Object.DestroyImmediate(fresh);
            EditorUtility.SetDirty(mat);
            return mat;
        }

        /// <summary>
        /// The creature's model: Generic, avatar from this model, Motion bone = root-motion node (a sibling of the
        /// skeleton: Unity leaves the motion node's own travel in the pose, so it must not be an ancestor of anything
        /// visible), sockets kept. Returns the avatar and the motion node's path.
        /// </summary>
        public static (Avatar avatar, string motionPath, GameObject model) ConfigureModel(string path,
            (string source, Material mat)[] remaps, StringBuilder log)
        {
            var imp = (ModelImporter)AssetImporter.GetAtPath(path);
            imp.importCameras = false;
            imp.importLights = false;
            imp.importAnimation = false;
            imp.importBlendShapes = false;
            imp.isReadable = false;
            imp.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            foreach (var (source, mat) in remaps)
                imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), source), mat);
            imp.animationType = ModelImporterAnimationType.Generic;
            imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            imp.optimizeGameObjects = false;
            imp.SaveAndReimport();
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            var motion = model.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == "Motion");
            string motionPath = motion != null ? AnimationUtility.CalculateTransformPath(motion, model.transform) : "";
            if (imp.motionNodeName != motionPath)
            {
                imp.motionNodeName = motionPath;
                imp.SaveAndReimport();
            }
            var avatar = AssetDatabase.LoadAllAssetsAtPath(path).OfType<Avatar>().FirstOrDefault();
            var smr = model.GetComponentInChildren<SkinnedMeshRenderer>();
            log.AppendLine($"{Path.GetFileName(path)}: avatar valid={avatar?.isValid} human={avatar?.isHuman} motion node='{motionPath}' " +
                           $"bones={smr?.bones.Length} tris={smr?.sharedMesh.triangles.Length / 3} " +
                           $"materials={string.Join("+", smr?.sharedMaterials.Select(m => m != null ? m.name : "null") ?? new string[0])}");
            log.AppendLine("  sockets: " + string.Join(", ", model.GetComponentsInChildren<Transform>(true)
                .Where(t => t.name.StartsWith("Socket_")).Select(t => t.name)));
            return (avatar, motionPath, model);
        }

        /// <summary>A static prop (no rig, no animation): materials remapped, nothing else imported.</summary>
        public static GameObject ConfigureStaticModel(string path, (string source, Material mat)[] remaps, StringBuilder log)
        {
            var imp = (ModelImporter)AssetImporter.GetAtPath(path);
            imp.importCameras = false;
            imp.importLights = false;
            imp.importAnimation = false;
            imp.importBlendShapes = false;
            imp.animationType = ModelImporterAnimationType.None;
            imp.isReadable = false;
            imp.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            foreach (var (source, mat) in remaps)
                imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), source), mat);
            imp.SaveAndReimport();
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            var mf = model.GetComponentInChildren<MeshFilter>();
            var mr = model.GetComponentInChildren<MeshRenderer>();
            log.AppendLine($"{Path.GetFileName(path)}: tris={(mf != null ? mf.sharedMesh.triangles.Length / 3 : 0)} " +
                           $"bounds={(mf != null ? mf.sharedMesh.bounds.size.ToString("F2") : "-")} " +
                           $"materials={string.Join("+", mr != null ? mr.sharedMaterials.Select(m => m != null ? m.name : "null") : new string[0])}");
            return model;
        }

        /// <summary><prefix>@<clip>.fbx: Generic, avatar copied from the model, one clip each; loop flags, root motion
        /// and events (functionName <paramref name="eventFunction"/>) from the JSON the Blender export writes.</summary>
        public static Dictionary<string, AnimationClip> ConfigureClips(string prefix, string jsonPath, Avatar avatar,
            string motionPath, string eventFunction, StringBuilder log)
        {
            var result = new Dictionary<string, AnimationClip>();
            var info = File.Exists(jsonPath) ? JsonUtility.FromJson<ClipList>(File.ReadAllText(jsonPath)) : new ClipList();
            var byName = (info.clips ?? Array.Empty<ClipInfo>()).ToDictionary(c => c.name);
            var lines = new List<string>();
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { Anims }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var file = Path.GetFileNameWithoutExtension(path);
                if (!file.StartsWith(prefix + "@")) continue;
                var clipName = file.Substring(file.IndexOf('@') + 1);
                byName.TryGetValue(clipName, out var ci);
                var imp = (ModelImporter)AssetImporter.GetAtPath(path);
                imp.importCameras = false;
                imp.importLights = false;
                imp.materialImportMode = ModelImporterMaterialImportMode.None;
                imp.preserveHierarchy = true;
                imp.animationType = ModelImporterAnimationType.Generic;
                imp.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                imp.sourceAvatar = avatar;
                imp.motionNodeName = motionPath;
                imp.importAnimation = true;
                imp.animationCompression = ModelImporterAnimationCompression.KeyframeReduction;
                imp.animationRotationError = 0.2f;
                imp.animationPositionError = 0.2f;
                imp.SaveAndReimport();
                var take = imp.importedTakeInfos.FirstOrDefault();
                if (string.IsNullOrEmpty(take.name))
                {
                    lines.Add($"{clipName}: NO TAKE");
                    continue;
                }
                float length = ci != null ? ci.frames / (float)ci.fps : take.stopTime - take.startTime;
                bool loop = ci != null && ci.loop, moves = ci != null && ci.rootMotion;
                var events = (ci?.events ?? Array.Empty<ClipEvent>()).Select(e => new AnimationEvent
                {
                    time = Mathf.Clamp01(e.time / Mathf.Max(length, 1e-3f)),      // importer events are normalised
                    functionName = eventFunction,
                    stringParameter = e.name,
                }).ToArray();
                imp.clipAnimations = new[]
                {
                    new ModelImporterClipAnimation
                    {
                        name = clipName,
                        takeName = take.name,
                        firstFrame = Mathf.Round(take.startTime * take.sampleRate),
                        lastFrame = Mathf.Round(take.stopTime * take.sampleRate),
                        loopTime = loop,
                        lockRootRotation = true, keepOriginalOrientation = true,
                        lockRootHeightY = true, keepOriginalPositionY = true,
                        lockRootPositionXZ = !moves, keepOriginalPositionXZ = true,
                        events = events,
                    },
                };
                imp.SaveAndReimport();
                var clip = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(c => c.name == clipName);
                if (clip == null)
                {
                    lines.Add(clipName + ": MISSING");
                    continue;
                }
                result[clipName] = clip;
                var ev = AnimationUtility.GetAnimationEvents(clip);
                lines.Add($"{clipName} {clip.length:0.00}s{(clip.isLooping ? " loop" : "")}" +
                          (moves ? $" rootspeed={clip.averageSpeed.magnitude:0.00}m/s dir={clip.averageSpeed.normalized:F2}" : "") +
                          (ev.Length > 0 ? " events=" + string.Join("/", ev.Select(e => $"{e.stringParameter}@{e.time:0.00}s")) : ""));
            }
            log.AppendLine($"  {prefix} clips: " + string.Join("; ", lines));
            return result;
        }

        public static InsectAnimationSet MakeSet(string name, PoolDef[] pools, Dictionary<string, AnimationClip> clips,
                                                 StringBuilder log)
        {
            var path = $"{SetDir}/{name}.asset";
            var set = AssetDatabase.LoadAssetAtPath<InsectAnimationSet>(path);
            if (set == null)
            {
                set = ScriptableObject.CreateInstance<InsectAnimationSet>();
                AssetDatabase.CreateAsset(set, path);
            }
            var missing = new List<string>();
            set.pools = pools.Select(p => new InsectAnimationSet.Pool
            {
                name = p.name,
                weight = p.w,
                clips = p.clips.Select(n =>
                {
                    if (clips.TryGetValue(n, out var c)) return c;
                    missing.Add(n);
                    return null;
                }).Where(c => c != null).ToArray(),
                moves = p.moves,
                hold = new Vector2(p.h0, p.h1),
                holdAfter = p.after,
                next = p.next,
                relocate = p.relocate,
            }).ToArray();
            EditorUtility.SetDirty(set);
            log.AppendLine("  animation set: " + path + (missing.Count > 0 ? " MISSING " + string.Join(", ", missing) : ""));
            return set;
        }

        /// <summary>Instance of the model with an Animator (root motion off until something drives it).</summary>
        public static GameObject NewCreature(GameObject model, Avatar avatar, string name)
        {
            var go = (GameObject)PrefabUtility.InstantiatePrefab(model);
            go.name = name;
            var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
            anim.avatar = avatar;
            anim.applyRootMotion = false;
            anim.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
            return go;
        }

        // ------------------------------------------------------------------------------------------------ scene bits
        public static void Lighting(float groundSize)
        {
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.intensity = 1.6f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(50, 200, 0);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.62f, 0.66f, 0.72f);
            RenderSettings.ambientEquatorColor = new Color(0.45f, 0.46f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.25f, 0.23f, 0.2f);
            var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.name = "Ground";
            ground.transform.localScale = new Vector3(groundSize / 10f, 1, groundSize / 10f);
            var gm = AssetDatabase.LoadAssetAtPath<Material>(Scenes + "/M_InsectGround.mat");
            if (gm == null)
            {
                gm = new Material(LitShader);
                AssetDatabase.CreateAsset(gm, Scenes + "/M_InsectGround.mat");
            }
            gm.color = new Color(0.40f, 0.38f, 0.26f);
            if (gm.HasProperty("_BaseColor")) gm.SetColor("_BaseColor", gm.color);
            if (gm.HasProperty("_Smoothness")) gm.SetFloat("_Smoothness", 0f);
            EditorUtility.SetDirty(gm);
            ground.GetComponent<Renderer>().sharedMaterial = gm;
        }

        public static Camera MakeCamera(string name, Vector3 pos, Vector3 target, float fov)
        {
            var cam = new GameObject(name).AddComponent<Camera>();
            cam.transform.position = pos;
            cam.transform.LookAt(target);
            cam.fieldOfView = fov;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 400f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.47f, 0.52f, 0.58f);
            return cam;
        }

        public static void Render(Camera cam, string dir, string file, int w, int h)
        {
            Directory.CreateDirectory(dir);
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            foreach (var smr in Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None))
                smr.forceMatrixRecalculationPerRender = true;
            var req = new RenderPipeline.StandardRequest { destination = rt };
            if (GraphicsSettings.currentRenderPipeline != null && RenderPipeline.SupportsRenderRequest(cam, req))
                RenderPipeline.SubmitRenderRequest(cam, req);
            else
            {
                cam.targetTexture = rt;
                cam.Render();
                cam.targetTexture = null;
            }
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prev;
            File.WriteAllBytes(Path.Combine(dir, file), tex.EncodeToPNG());
            Object.DestroyImmediate(tex);
            rt.Release();
        }

        public static Type FindType(string fullName) =>
            AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType(fullName)).FirstOrDefault(t => t != null);
    }
}
