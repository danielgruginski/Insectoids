using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Insectoids
{
    /// <summary>
    /// A splat of web where a glob landed: it snaps open to <see cref="Radius"/>, holds for its duration and fades.
    /// Gameplay hook: <see cref="Created"/> fires once per snare, <see cref="All"/> lists the live ones and
    /// <see cref="IsSnared"/> tells whether a point is inside any of them (slow or root units there). Pooled.
    /// </summary>
    public class SpiderWebSnare : MonoBehaviour
    {
        public static readonly List<SpiderWebSnare> All = new List<SpiderWebSnare>();
        /// <summary>A snare opened (it knows the spider that spat it).</summary>
        public static event Action<SpiderWebSnare> Created;

        public SpiderCombat Owner { get; private set; }
        public float Radius { get; private set; }
        /// <summary>0..1 while it lasts (fades out at the end).</summary>
        public float Strength { get; private set; }

        float age, duration;
        MeshRenderer disc;
        MaterialPropertyBlock mpb;
        static readonly Stack<SpiderWebSnare> pool = new Stack<SpiderWebSnare>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetPool()
        {
            pool.Clear();
            All.Clear();
        }

        public static SpiderWebSnare Spawn(SpiderCombat owner, Vector3 p, Vector3 normal, float radius, float seconds, Material mat)
        {
            SpiderWebSnare s = null;
            while (s == null && pool.Count > 0) s = pool.Pop();
            if (s == null)
            {
                s = new GameObject("FX_WebSnare").AddComponent<SpiderWebSnare>();
                s.transform.SetParent(SpiderFx.Container, false);
                s.mpb = new MaterialPropertyBlock();
                s.gameObject.AddComponent<MeshFilter>().sharedMesh = SpiderFx.DiscMesh();
                s.disc = s.gameObject.AddComponent<MeshRenderer>();
                s.disc.shadowCastingMode = ShadowCastingMode.Off;
                s.disc.receiveShadows = false;
                s.disc.lightProbeUsage = LightProbeUsage.Off;
            }
            s.disc.sharedMaterial = mat;
            s.Owner = owner;
            s.Radius = radius;
            s.duration = seconds;
            s.age = 0;
            var up = normal.sqrMagnitude > 1e-4f ? normal.normalized : Vector3.up;
            var fwd = Vector3.ProjectOnPlane(UnityEngine.Random.onUnitSphere, up);
            if (fwd.sqrMagnitude < 1e-4f) fwd = Vector3.Cross(up, Vector3.right);
            s.transform.SetPositionAndRotation(p + up * 0.02f, Quaternion.LookRotation(fwd, up));
            s.transform.localScale = Vector3.one * 0.01f;
            s.gameObject.SetActive(true);
            All.Add(s);
            Created?.Invoke(s);
            return s;
        }

        /// <summary>Is the point inside a live snare (flat distance)?</summary>
        public static bool IsSnared(Vector3 p)
        {
            foreach (var s in All)
            {
                var d = p - s.transform.position;
                d.y = 0;
                if (d.sqrMagnitude <= s.Radius * s.Radius * 0.8f && s.Strength > 0.3f) return true;
            }
            return false;
        }

        void Update()
        {
            if (disc == null || mpb == null) { Destroy(gameObject); return; }      // a copy without its setup
            age += Time.deltaTime;
            float open = Mathf.Clamp01(age / 0.18f);
            float k = 1f + 0.12f * Mathf.Sin(open * Mathf.PI) ;           // a little overshoot as it slaps open
            transform.localScale = Vector3.one * Radius * Mathf.Lerp(0.2f, 1f, open) * k;
            float fadeStart = duration - 1.5f;
            Strength = age < fadeStart ? 1f : Mathf.Clamp01(1f - (age - fadeStart) / 1.5f);
            SpiderFx.Tint(disc, mpb, new Color(1f, 1f, 1f, 0.95f * Strength));
            if (age >= duration) Recycle();
        }

        void Recycle()
        {
            All.Remove(this);
            gameObject.SetActive(false);
            pool.Push(this);
        }

        void OnDisable() => All.Remove(this);
    }
}
