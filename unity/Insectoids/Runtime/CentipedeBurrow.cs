using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Insectoids
{
    /// <summary>
    /// The centipede's Burrow and Emerge clips call <c>OnInsectEvent("Burrow" / "Emerge")</c> when the head crosses the
    /// ground. This opens a dark hole there (it stays <see cref="holeSeconds"/>, then fades) and throws out a burst of
    /// dirt clods. <see cref="Burrowed"/> / <see cref="Emerged"/> fire with the hole's position for gameplay (the
    /// centipede is underground and untargetable between them). Holes and clods are pooled.
    /// </summary>
    public class CentipedeBurrow : MonoBehaviour
    {
        public Material holeMaterial, dirtMaterial;
        public float holeRadius = 0.55f;
        public float holeSeconds = 6f;
        public int clods = 12;

        public event Action<CentipedeBurrow, Vector3> Burrowed, Emerged;
        public bool Underground { get; private set; }

        Transform mouth;
        static Texture2D holeTex;

        void Awake()
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (t.name == "Socket_Mouth") mouth = t;
        }

        public void OnInsectEvent(string name)
        {
            if (name != "Burrow" && name != "Emerge") return;
            Underground = name == "Burrow";
            if (!SpiderFx.CanSpawn) return;
            var p = mouth != null ? mouth.position : transform.position;
            var ground = p;
            if (Physics.Raycast(p + Vector3.up * 3f, Vector3.down, out var hit, 10f, ~0, QueryTriggerInteraction.Ignore))
                ground = hit.point;
            else
                ground.y = transform.position.y;
            float s = transform.lossyScale.x;
            Hole.Open(ground, holeRadius * s, holeSeconds, holeMaterial != null ? holeMaterial : DefaultHoleMaterial());
            Clod.Burst(ground, clods, 0.09f * s, dirtMaterial);
            if (Underground) Burrowed?.Invoke(this, ground);
            else Emerged?.Invoke(this, ground);
        }

        /// <summary>A soft dark hole with a ring of pale churned dirt around it.</summary>
        public static Texture2D HoleTexture(int size = 128)
        {
            if (holeTex != null) return holeTex;
            holeTex = new Texture2D(size, size, TextureFormat.RGBA32, true) { name = "CentipedeHole", wrapMode = TextureWrapMode.Clamp };
            var px = new Color32[size * size];
            var rng = new System.Random(9);
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    float dx = (x + 0.5f) / size * 2f - 1f, dy = (y + 0.5f) / size * 2f - 1f;
                    float a = Mathf.Atan2(dy, dx);
                    float r = Mathf.Sqrt(dx * dx + dy * dy) * (1f + 0.08f * Mathf.Sin(a * 5f) + 0.05f * Mathf.Sin(a * 11f + 1f));
                    float hole = Mathf.Clamp01((0.55f - r) / 0.15f);
                    float rim = Mathf.Clamp01(1f - Mathf.Abs(r - 0.72f) / 0.2f) * (0.7f + 0.3f * (float)rng.NextDouble());
                    float alpha = Mathf.Clamp01(Mathf.Max(hole, rim * 0.85f)) * Mathf.Clamp01((1f - r) / 0.12f);
                    var dark = new Color(0.06f, 0.045f, 0.03f);
                    var dirt = new Color(0.42f, 0.33f, 0.22f);
                    var c = Color.Lerp(dirt, dark, hole);
                    px[y * size + x] = new Color(c.r, c.g, c.b, alpha);
                }
            holeTex.SetPixels32(px);
            holeTex.Apply(true);
            return holeTex;
        }

        static Material defHole;
        static Material DefaultHoleMaterial() => defHole != null ? defHole : defHole = SpiderFx.AlphaMaterial(HoleTexture(), "CentipedeHole");

        class Hole : MonoBehaviour
        {
            float age, life, radius;
            MeshRenderer mr;
            MaterialPropertyBlock mpb;
            static readonly Stack<Hole> pool = new Stack<Hole>();

            [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
            static void ResetPool() => pool.Clear();

            public static void Open(Vector3 p, float radius, float life, Material mat)
            {
                Hole h = null;
                while (h == null && pool.Count > 0) h = pool.Pop();
                if (h == null)
                {
                    var go = new GameObject("FX_BurrowHole");
                    go.transform.SetParent(SpiderFx.Container, false);
                    go.AddComponent<MeshFilter>().sharedMesh = SpiderFx.DiscMesh();
                    var r = go.AddComponent<MeshRenderer>();
                    r.shadowCastingMode = ShadowCastingMode.Off;
                    r.receiveShadows = false;
                    h = go.AddComponent<Hole>();
                }
                h.Init();
                h.mr.sharedMaterial = mat;
                h.age = 0;
                h.life = life;
                h.radius = radius;
                h.transform.SetPositionAndRotation(p + Vector3.up * 0.015f, Quaternion.Euler(0, UnityEngine.Random.value * 360f, 0));
                h.gameObject.SetActive(true);
            }

            internal void Init()
            {
                if (mr == null) mr = GetComponent<MeshRenderer>();
                if (mpb == null) mpb = new MaterialPropertyBlock();
            }

            void Update()
            {
                if (mr == null) { Destroy(gameObject); return; }     // a copy without its setup: drop it
                age += Time.deltaTime;
                float open = Mathf.Clamp01(age / 0.25f);
                transform.localScale = Vector3.one * radius * Mathf.Lerp(0.3f, 1f, 1f - (1f - open) * (1f - open));
                float fade = Mathf.Clamp01((life - age) / 1.5f);
                SpiderFx.Tint(mr, mpb, new Color(1, 1, 1, fade));
                if (age >= life)
                {
                    gameObject.SetActive(false);
                    pool.Push(this);
                }
            }
        }

        class Clod : MonoBehaviour
        {
            Vector3 vel, spin;
            float age, size;
            static readonly Stack<Clod> pool = new Stack<Clod>();
            static Material fallback;

            [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
            static void ResetPool() => pool.Clear();

            public static void Burst(Vector3 p, int n, float size, Material mat)
            {
                if (mat == null) mat = fallback != null ? fallback : fallback = DirtFallback();
                for (int i = 0; i < n; i++)
                {
                    Clod c = null;
                    while (c == null && pool.Count > 0) c = pool.Pop();
                    if (c == null)
                    {
                        c = new GameObject("FX_Clod").AddComponent<Clod>();
                        c.transform.SetParent(SpiderFx.Container, false);
                        c.gameObject.AddComponent<MeshFilter>().sharedMesh = SpiderFx.GlobMesh();
                        var mr = c.gameObject.AddComponent<MeshRenderer>();
                        mr.shadowCastingMode = ShadowCastingMode.Off;
                    }
                    c.GetComponent<MeshRenderer>().sharedMaterial = mat;
                    float a = UnityEngine.Random.value * Mathf.PI * 2f;
                    float out_ = UnityEngine.Random.Range(1.2f, 2.8f);
                    c.vel = new Vector3(Mathf.Cos(a) * out_, UnityEngine.Random.Range(2.5f, 4.5f), Mathf.Sin(a) * out_);
                    c.spin = UnityEngine.Random.insideUnitSphere * 540f;
                    c.size = size * UnityEngine.Random.Range(0.6f, 1.4f);
                    c.age = 0;
                    c.transform.position = p + new Vector3(Mathf.Cos(a), 0.3f, Mathf.Sin(a)) * 0.15f;
                    c.transform.localScale = Vector3.one * c.size;
                    c.gameObject.SetActive(true);
                }
            }

            static Material DirtFallback()
            {
                var m = SpiderFx.SilkMaterial("CentipedeDirt");
                var c = new Color(0.36f, 0.28f, 0.19f);
                m.color = c;
                if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
                if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.05f);
                return m;
            }

            void Update()
            {
                float dt = Time.deltaTime;
                age += dt;
                vel += Physics.gravity * dt;
                transform.position += vel * dt;
                transform.Rotate(spin * dt);
                if (age > 0.9f) transform.localScale = Vector3.one * size * Mathf.Clamp01(1f - (age - 0.9f) / 0.4f);
                if (age > 1.3f || transform.position.y < -1f)
                {
                    gameObject.SetActive(false);
                    pool.Push(this);
                }
            }
        }
    }
}
