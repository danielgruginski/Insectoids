using System;
using UnityEngine;

namespace Insectoids
{
    /// <summary>
    /// The spider's end of its clips: receives the animation events (Bite, Strike, Spit, Dead) and fires the web glob.
    ///
    /// The clips carry events calling <c>OnInsectEvent(name)</c> at the moment of impact (Bite 0.50 s, Strike 0.73 s,
    /// Spit 0.67 s, Dead 1.75 s). Hook damage and sound to <see cref="EventFired"/>; the web spit is handled here:
    /// a glob of silk is lobbed from Socket_Spinneret on a ballistic arc to <see cref="target"/> (or the nearest
    /// <see cref="SpiderPrey"/> in front, or a point ahead), trailing a silk thread, and lands as a
    /// <see cref="SpiderWebSnare"/> that holds whatever is inside it.
    /// </summary>
    public class SpiderCombat : MonoBehaviour
    {
        [Header("Web spit")]
        public Transform target;
        [Tooltip("Without a target: aim at the nearest SpiderPrey in front of the spider, within spitRange.")]
        public bool autoTarget = true;
        public Vector2 spitRange = new Vector2(4f, 12f);
        [Tooltip("Seconds of flight per metre of distance (plus a fixed 0.35 s): lower = flatter, faster lob.")]
        public float flightPerMetre = 0.06f;
        public float globSize = 0.16f;
        public float snareRadius = 1.3f;
        public float snareSeconds = 8f;
        public Material silkMaterial, webMaterial, threadMaterial;

        /// <summary>Every animation event by name (Bite, Strike, Spit, Dead).</summary>
        public event Action<SpiderCombat, string> EventFired;
        /// <summary>A glob left the spinnerets: (origin, aim point).</summary>
        public event Action<SpiderCombat, Vector3, Vector3> Spat;

        public Transform Spinneret { get; private set; }
        public Transform Mouth { get; private set; }

        void Awake()
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                if (t.name == "Socket_Spinneret") Spinneret = t;
                else if (t.name == "Socket_Mouth") Mouth = t;
            }
        }

        /// <summary>Called by the clips' animation events.</summary>
        public void OnInsectEvent(string name) => OnSpiderEvent(name);

        public void OnSpiderEvent(string name)
        {
            EventFired?.Invoke(this, name);
            if (name == "Spit") Spit();
        }

        /// <summary>Lob a glob now: at <paramref name="at"/>, else at the target / nearest prey / a point ahead.</summary>
        public void Spit(Vector3? at = null)
        {
            if (!SpiderFx.CanSpawn) return;
            var from = Spinneret != null ? Spinneret.position : transform.position + Vector3.up;
            var aim = at ?? AimPoint();
            float s = transform.lossyScale.x;
            float dist = Vector3.Distance(new Vector3(from.x, 0, from.z), new Vector3(aim.x, 0, aim.z));
            float T = 0.35f + flightPerMetre * dist;
            var v = (aim - from) / T - 0.5f * Physics.gravity * T;
            SpiderWebGlob.Launch(this, from, v, globSize * s, snareRadius * s, snareSeconds);
            Spat?.Invoke(this, from, aim);
        }

        Vector3 AimPoint()
        {
            if (target != null) return target.position;
            float s = transform.lossyScale.x;
            if (autoTarget)
            {
                Transform best = null;
                float bestD = float.MaxValue;
                foreach (var p in SpiderPrey.All)
                {
                    if (p == null || !p.isActiveAndEnabled) continue;
                    var d = p.transform.position - transform.position;
                    d.y = 0;
                    float m = d.magnitude;
                    if (m < spitRange.x * s || m > spitRange.y * s) continue;
                    if (Vector3.Angle(transform.forward, d) > 70f) continue;
                    if (m < bestD) { bestD = m; best = p.transform; }
                }
                if (best != null) return best.position;
            }
            var ahead = transform.position + transform.forward * UnityEngine.Random.Range(spitRange.x, spitRange.y) * s;
            if (Physics.Raycast(ahead + Vector3.up * 20f, Vector3.down, out var hit, 40f, ~0, QueryTriggerInteraction.Ignore))
                return hit.point;
            return new Vector3(ahead.x, transform.position.y, ahead.z);
        }
    }
}
