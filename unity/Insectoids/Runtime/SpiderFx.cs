using UnityEngine;
using UnityEngine.Rendering;

namespace Insectoids
{
    /// <summary>
    /// Shared pieces for the spider's web effects: a procedural orb-web texture, alpha-blended and lit materials,
    /// a lumpy glob mesh and a flat disc. Effect objects are named FX_*.
    /// </summary>
    public static class SpiderFx
    {
        static Texture2D web;
        static Mesh glob, disc;
        static Material webFallback, silkFallback, lineFallback;
        static Transform container;

        /// <summary>Effects only exist in Play mode: animation events also fire when clips are previewed or evaluated in
        /// edit mode, and anything spawned then would stay in the scene (its Update never runs) and get saved.</summary>
        public static bool CanSpawn => Application.isPlaying;

        /// <summary>Parent of every pooled effect object, so they stay out of the scene root.</summary>
        public static Transform Container
        {
            get
            {
                if (container == null) container = new GameObject("FX_Insectoids").transform;
                return container;
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => container = null;     // Enter Play Mode without a domain reload

        /// <summary>Off-white orb web on transparent: 18 slightly irregular spokes and a sagging spiral, fading at the rim.</summary>
        public static Texture2D WebTexture(int size = 256)
        {
            if (web != null) return web;
            web = new Texture2D(size, size, TextureFormat.RGBA32, true) { name = "SpiderWeb", wrapMode = TextureWrapMode.Clamp };
            var rng = new System.Random(5);
            const int spokes = 18;
            var ang = new float[spokes];
            for (int i = 0; i < spokes; i++) ang[i] = (i + (float)rng.NextDouble() * 0.35f - 0.17f) * Mathf.PI * 2f / spokes;
            var px = new Color32[size * size];
            float pix = 2f / size;                                      // one texel in the -1..1 square
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    float dx = (x + 0.5f) / size * 2f - 1f, dy = (y + 0.5f) / size * 2f - 1f;
                    float r = Mathf.Sqrt(dx * dx + dy * dy);
                    float a = Mathf.Atan2(dy, dx);
                    if (a < 0) a += Mathf.PI * 2f;
                    float best = 10f, gap = Mathf.PI * 2f / spokes;
                    foreach (var s in ang)
                    {
                        float d = Mathf.Abs(Mathf.DeltaAngle(a * Mathf.Rad2Deg, s * Mathf.Rad2Deg)) * Mathf.Deg2Rad;
                        best = Mathf.Min(best, d);
                    }
                    float spokeDist = best * r;                         // distance to the nearest spoke, in the square
                    float spoke = Mathf.Clamp01(1.4f - spokeDist / (pix * 0.9f));
                    // spiral: straight threads between spokes sag toward the centre
                    float sag = 1f - 0.07f * Mathf.Sin(Mathf.Clamp01(best / (gap * 0.5f)) * Mathf.PI * 0.5f);
                    float rr = r / sag;
                    float turns = rr / 0.075f + a / (Mathf.PI * 2f);
                    float ring = Mathf.Abs(turns - Mathf.Round(turns)) * 0.075f;
                    float spiral = Mathf.Clamp01(1.3f - ring / (pix * 0.85f)) * (rr > 0.12f ? 1f : 0f);
                    float hub = Mathf.Clamp01(1f - r / 0.1f) * 0.55f;
                    float fade = Mathf.Clamp01((0.98f - r) / 0.1f);
                    float alpha = Mathf.Clamp01(Mathf.Max(spoke, spiral * 0.85f, hub)) * fade;
                    byte shade = (byte)(215 + rng.Next(0, 30));
                    px[y * size + x] = new Color32(shade, shade, (byte)(shade - 12), (byte)(alpha * 255));
                }
            web.SetPixels32(px);
            web.Apply(true);
            return web;
        }

        /// <summary>URP Particles/Unlit, alpha blended, two-sided, no depth write; tint and fade through _BaseColor.</summary>
        public static Material AlphaMaterial(Texture tex, string name)
        {
            var sh = Shader.Find("Universal Render Pipeline/Particles/Unlit") ?? Shader.Find("Sprites/Default");
            var m = new Material(sh) { name = name };
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 0f);                                   // alpha
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_ZWrite", 0f);
            m.SetFloat("_Cull", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            if (tex != null)
            {
                m.SetTexture("_BaseMap", tex);
                m.mainTexture = tex;
            }
            m.SetColor("_BaseColor", Color.white);
            return m;
        }

        /// <summary>Wet, sticky silk for the glob: the pipeline's lit shader, off-white and fairly glossy.</summary>
        public static Material SilkMaterial(string name = "SpiderSilk")
        {
            var sh = GraphicsSettings.currentRenderPipeline != null ? GraphicsSettings.currentRenderPipeline.defaultShader
                                                                     : Shader.Find("Standard");
            var m = new Material(sh) { name = name };
            var c = new Color(0.9f, 0.88f, 0.8f);
            m.color = c;
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.7f);
            return m;
        }

        public static Material WebFallback => webFallback != null ? webFallback : webFallback = AlphaMaterial(WebTexture(), "SpiderWeb");
        public static Material SilkFallback => silkFallback != null ? silkFallback : silkFallback = SilkMaterial();
        public static Material LineFallback => lineFallback != null ? lineFallback : lineFallback = AlphaMaterial(null, "SpiderSilkLine");

        /// <summary>A lumpy ball of radius ~1 (scale it to the glob size).</summary>
        public static Mesh GlobMesh()
        {
            if (glob != null) return glob;
            const int lat = 6, lon = 9;
            var rng = new System.Random(3);
            var v = new Vector3[(lat + 1) * lon];
            for (int i = 0; i <= lat; i++)
                for (int j = 0; j < lon; j++)
                {
                    float th = Mathf.PI * i / lat, ph = Mathf.PI * 2f * j / lon;
                    float k = (i == 0 || i == lat) ? 1f : 0.85f + 0.3f * (float)rng.NextDouble();
                    v[i * lon + j] = new Vector3(Mathf.Sin(th) * Mathf.Cos(ph), Mathf.Cos(th), Mathf.Sin(th) * Mathf.Sin(ph)) * k;
                }
            var tri = new System.Collections.Generic.List<int>();
            for (int i = 0; i < lat; i++)
                for (int j = 0; j < lon; j++)
                {
                    int a = i * lon + j, b = i * lon + (j + 1) % lon, c = (i + 1) * lon + j, d = (i + 1) * lon + (j + 1) % lon;
                    tri.AddRange(new[] { a, b, c, b, d, c });
                }
            glob = new Mesh { name = "FX_Glob", vertices = v, triangles = tri.ToArray() };
            glob.RecalculateNormals();
            glob.RecalculateBounds();
            return glob;
        }

        /// <summary>A square of side 2 in the XZ plane (radius 1 disc for a round texture), facing +Y.</summary>
        public static Mesh DiscMesh()
        {
            if (disc != null) return disc;
            disc = new Mesh { name = "FX_Disc" };
            disc.vertices = new[] { new Vector3(-1, 0, -1), new Vector3(1, 0, -1), new Vector3(1, 0, 1), new Vector3(-1, 0, 1) };
            disc.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) };
            disc.triangles = new[] { 0, 2, 1, 0, 3, 2 };
            disc.RecalculateNormals();
            disc.RecalculateBounds();
            return disc;
        }

        public static void Tint(Renderer r, MaterialPropertyBlock mpb, Color c)
        {
            if (r == null || mpb == null) return;
            mpb.SetColor("_BaseColor", c);
            r.SetPropertyBlock(mpb);
        }
    }
}
