using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Insectoids
{
    /// <summary>
    /// A glob of silk in flight: ballistic, wobbling, trailing a silk thread back to the spinnerets. On the first
    /// collider it meets (or at the ground height it was aimed at) it bursts into a <see cref="SpiderWebSnare"/>.
    /// Pooled.
    /// </summary>
    public class SpiderWebGlob : MonoBehaviour
    {
        SpiderCombat owner;
        Vector3 vel;
        float size, radius, seconds, age, threadFade = -1f;
        Vector3 threadEnd;
        Transform ball;
        LineRenderer thread;
        MaterialPropertyBlock mpb;
        static readonly Stack<SpiderWebGlob> pool = new Stack<SpiderWebGlob>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetPool() => pool.Clear();

        public static SpiderWebGlob Launch(SpiderCombat owner, Vector3 from, Vector3 velocity, float size, float snareRadius,
                                           float snareSeconds)
        {
            SpiderWebGlob g = null;
            while (g == null && pool.Count > 0) g = pool.Pop();
            if (g == null)
            {
                g = new GameObject("FX_WebGlob").AddComponent<SpiderWebGlob>();
                g.transform.SetParent(SpiderFx.Container, false);
                g.Build(owner);
            }
            g.owner = owner;
            g.vel = velocity;
            g.size = size;
            g.radius = snareRadius;
            g.seconds = snareSeconds;
            g.age = 0;
            g.threadFade = -1f;
            g.transform.position = from;
            g.ball.gameObject.SetActive(true);
            g.gameObject.SetActive(true);
            g.thread.enabled = true;
            g.thread.widthMultiplier = 0.035f * size / 0.16f;
            SpiderFx.Tint(g.thread, g.mpb, new Color(0.95f, 0.94f, 0.88f, 0.85f));
            return g;
        }

        void Build(SpiderCombat o)
        {
            mpb = new MaterialPropertyBlock();
            var b = new GameObject("FX_Glob");
            b.transform.SetParent(transform, false);
            b.AddComponent<MeshFilter>().sharedMesh = SpiderFx.GlobMesh();
            var mr = b.AddComponent<MeshRenderer>();
            mr.sharedMaterial = o.silkMaterial != null ? o.silkMaterial : SpiderFx.SilkFallback;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            ball = b.transform;
            thread = gameObject.AddComponent<LineRenderer>();
            thread.sharedMaterial = o.threadMaterial != null ? o.threadMaterial : SpiderFx.LineFallback;
            thread.positionCount = 2;
            thread.useWorldSpace = true;
            thread.alignment = LineAlignment.View;
            thread.shadowCastingMode = ShadowCastingMode.Off;
            thread.receiveShadows = false;
            thread.numCapVertices = 0;
        }

        Vector3 ThreadStart => owner != null && owner.Spinneret != null ? owner.Spinneret.position : threadEnd;

        void Update()
        {
            if (ball == null || thread == null || mpb == null) { Destroy(gameObject); return; }   // a copy without its setup
            float dt = Time.deltaTime;
            age += dt;
            if (threadFade >= 0f)                             // landed: the thread sags and fades
            {
                threadFade += dt / 0.6f;
                thread.SetPosition(0, Vector3.Lerp(thread.GetPosition(0), threadEnd, dt * 2f));
                SpiderFx.Tint(thread, mpb, new Color(0.95f, 0.94f, 0.88f, 0.85f * (1f - threadFade)));
                if (threadFade >= 1f) Recycle();
                return;
            }
            vel += Physics.gravity * dt;
            var step = vel * dt;
            if (Physics.Raycast(transform.position, step.normalized, out var hit, step.magnitude + 1e-3f, ~0,
                                QueryTriggerInteraction.Ignore))
            {
                Land(hit.point, hit.normal);
                return;
            }
            transform.position += step;
            if (transform.position.y < -20f || age > 6f)
            {
                Land(transform.position, Vector3.up);
                return;
            }
            float wob = 1f + 0.12f * Mathf.Sin(age * 31f);
            ball.localScale = new Vector3(size * wob, size / wob, size * wob);
            ball.rotation = Quaternion.LookRotation(vel.sqrMagnitude > 1e-4f ? vel : Vector3.forward);
            thread.SetPosition(0, ThreadStart);
            thread.SetPosition(1, transform.position);
        }

        void Land(Vector3 p, Vector3 n)
        {
            SpiderWebSnare.Spawn(owner, p, n, radius, seconds,
                                 owner != null && owner.webMaterial != null ? owner.webMaterial : SpiderFx.WebFallback);
            ball.gameObject.SetActive(false);
            threadEnd = p;
            thread.SetPosition(0, ThreadStart);
            thread.SetPosition(1, p);
            threadFade = 0f;
        }

        void Recycle()
        {
            thread.enabled = false;
            gameObject.SetActive(false);
            pool.Push(this);
        }
    }
}
