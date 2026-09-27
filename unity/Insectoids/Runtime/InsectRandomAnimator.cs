using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace Insectoids
{
    /// <summary>
    /// Plays random clips from an <see cref="InsectAnimationSet"/> through a small playable graph (two-slot crossfade),
    /// for Generic rigs. Root-motion pools move the creature; it meanders, steers back toward <see cref="home"/> when it
    /// strays past <see cref="wanderRadius"/>, and keeps <see cref="separation"/> from the others.
    /// For looking at the animation; a game would drive clips from its own state machine.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class InsectRandomAnimator : MonoBehaviour
    {
        public InsectAnimationSet set;
        public float crossfade = 0.2f;
        public Vector3 home;
        public float wanderRadius = 12f;
        [Tooltip("Keep this far from other creatures (metres, before scale).")]
        public float separation = 2.6f;
        public Vector2 speedRange = new Vector2(0.94f, 1.06f);
        [Tooltip("Label height above the root, for viewers.")]
        public float labelHeight = 1.4f;

        public string CurrentClip { get; private set; } = "";
        public string CurrentPool => pool != null ? pool.name : "";
        public float CurrentTime => cur.IsValid() ? (float)cur.GetTime() : 0f;
        public static readonly List<InsectRandomAnimator> All = new List<InsectRandomAnimator>();

        Animator anim;
        PlayableGraph graph;
        AnimationMixerPlayable mixer;
        AnimationClipPlayable cur, prev;
        float fade = 1, stepEnd, speed, seed;
        InsectAnimationSet.Pool pool;
        int step;

        void OnEnable()
        {
            All.Add(this);
            anim = GetComponent<Animator>();
            anim.applyRootMotion = true;
            graph = PlayableGraph.Create(name + "_Random");
            graph.SetTimeUpdateMode(DirectorUpdateMode.GameTime);
            var output = AnimationPlayableOutput.Create(graph, "Animation", anim);
            mixer = AnimationMixerPlayable.Create(graph, 2);
            output.SetSourcePlayable(mixer);
            graph.Play();
            speed = Random.Range(speedRange.x, speedRange.y);
            seed = Random.value * 100f;
            if (set != null) Restart();
        }

        void OnDisable()
        {
            All.Remove(this);
            if (graph.IsValid()) graph.Destroy();
        }

        public void Restart() => StartPool(set.PickWeighted());

        /// <summary>Jump to a named pool (e.g. from a test UI). Returns false if the set has no such pool.</summary>
        public bool PlayPool(string poolName)
        {
            var p = set != null ? set.Get(poolName) : null;
            if (p == null || p.clips == null || p.clips.Length == 0) return false;
            StartPool(p);
            return true;
        }

        void StartPool(InsectAnimationSet.Pool p)
        {
            pool = p;
            step = 0;
            Play(p.sequence ? p.clips[0] : p.clips[Random.Range(0, p.clips.Length)]);
        }

        void Play(AnimationClip clip)
        {
            if (prev.IsValid())
            {
                graph.Disconnect(mixer, 1);
                prev.Destroy();
            }
            if (cur.IsValid())
            {
                graph.Disconnect(mixer, 0);
                graph.Connect(cur, 0, mixer, 1);
                prev = cur;
            }
            cur = AnimationClipPlayable.Create(graph, clip);
            cur.SetSpeed(speed);
            graph.Connect(cur, 0, mixer, 0);
            fade = prev.IsValid() ? 0 : 1;
            mixer.SetInputWeight(0, fade);
            mixer.SetInputWeight(1, 1 - fade);
            CurrentClip = clip.name;
            float dur = clip.isLooping ? Random.Range(pool.hold.x, pool.hold.y)
                                       : clip.length / speed - crossfade * 0.5f + pool.holdAfter;
            stepEnd = Time.time + Mathf.Max(0.2f, dur);
        }

        void Update()
        {
            if (set == null || !graph.IsValid() || pool == null) return;
            if (fade < 1)
            {
                fade = Mathf.Min(1, fade + Time.deltaTime / Mathf.Max(crossfade, 0.01f));
                mixer.SetInputWeight(0, fade);
                mixer.SetInputWeight(1, 1 - fade);
            }
            if (Time.time < stepEnd) return;
            if (pool.sequence && step + 1 < pool.clips.Length)
                Play(pool.clips[++step]);
            else
            {
                if (pool.relocate.y > 0) Relocate(pool.relocate);
                var next = string.IsNullOrEmpty(pool.next) ? null : set.Get(pool.next);
                StartPool(next != null && next.clips.Length > 0 ? next : set.PickWeighted());
            }
        }

        /// <summary>Move while hidden (e.g. underground): a random distance in range, heading toward home when far out.</summary>
        void Relocate(Vector2 range)
        {
            float d = Random.Range(range.x, range.y) * transform.lossyScale.x;
            var dir = Quaternion.Euler(0, Random.Range(0f, 360f), 0) * Vector3.forward;
            var toHome = home - transform.position;
            toHome.y = 0;
            if (toHome.magnitude > wanderRadius * 0.5f) dir = Vector3.Slerp(dir, toHome.normalized, 0.7f).normalized;
            transform.position += dir * d;
            transform.rotation = Quaternion.Euler(0, Random.Range(0f, 360f), 0);
        }

        void OnAnimatorMove()
        {
            var dp = anim.deltaPosition;
            dp.y = 0;
            transform.position += dp;
            transform.rotation *= anim.deltaRotation;
            if (pool == null || !pool.moves) return;
            var toHome = home - transform.position;
            toHome.y = 0;
            float d = toHome.magnitude;
            if (d > wanderRadius * 0.6f)
            {
                var target = Quaternion.LookRotation(toHome.normalized, Vector3.up);
                float urgency = Mathf.InverseLerp(wanderRadius * 0.6f, wanderRadius, d);
                transform.rotation = Quaternion.RotateTowards(transform.rotation, target, (35f + 110f * urgency) * Time.deltaTime);
                return;
            }
            float turn = (Mathf.PerlinNoise(Time.time * 0.3f, seed) * 2f - 1f) * 50f;     // lazy meander
            float sep = separation * transform.lossyScale.x;
            foreach (var o in All)                                                       // step around the others
            {
                if (o == this) continue;
                var away = transform.position - o.transform.position;
                away.y = 0;
                if (away.sqrMagnitude < sep * sep * 1.6f && Vector3.Dot(transform.forward, -away) > 0)
                    turn += Vector3.SignedAngle(transform.forward, away, Vector3.up) > 0 ? 80f : -80f;
            }
            transform.Rotate(0, turn * Time.deltaTime, 0);
        }

        void LateUpdate()
        {
            float sep = separation * transform.lossyScale.x;
            foreach (var o in All)                      // no standing inside each other
            {
                if (o == this) continue;
                var away = transform.position - o.transform.position;
                away.y = 0;
                float m = away.magnitude;
                float want = (sep + o.separation * o.transform.lossyScale.x) * 0.35f;
                if (m < want && m > 1e-4f) transform.position += away / m * (want - m) * 0.5f;
            }
        }
    }
}
