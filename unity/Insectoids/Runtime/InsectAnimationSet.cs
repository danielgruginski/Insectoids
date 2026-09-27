using System;
using UnityEngine;

namespace Insectoids
{
    /// <summary>
    /// Weighted pools of clips for <see cref="InsectRandomAnimator"/>. A pool plays one random clip, or all of its
    /// clips in order when <see cref="Pool.sequence"/> is set. Looping clips are held for a random time inside
    /// <see cref="Pool.hold"/>.
    /// </summary>
    [CreateAssetMenu(menuName = "Insectoids/Animation Set")]
    public class InsectAnimationSet : ScriptableObject
    {
        [Serializable]
        public class Pool
        {
            public string name;
            [Min(0)] public float weight = 1;
            public AnimationClip[] clips;
            [Tooltip("Play the clips in order instead of picking one.")]
            public bool sequence;
            [Tooltip("Root-motion locomotion: the creature steers while this plays.")]
            public bool moves;
            [Tooltip("Seconds a looping clip is held.")]
            public Vector2 hold = new Vector2(3, 6);
            [Tooltip("Seconds to hold the last frame of a one-shot clip (e.g. lying dead).")]
            public float holdAfter;
            [Tooltip("Pool to play next; empty = pick a random pool.")]
            public string next;
            [Tooltip("After this pool, move the creature this far (random within the range, random heading) before the next "
                     + "one: a burrowed centipede travels underground and surfaces somewhere else. 0 = stay.")]
            public Vector2 relocate;
        }

        public Pool[] pools = Array.Empty<Pool>();

        public Pool Get(string poolName) => Array.Find(pools, p => p.name == poolName);

        public Pool PickWeighted()
        {
            float total = 0;
            foreach (var p in pools) if (p.clips != null && p.clips.Length > 0) total += p.weight;
            float r = UnityEngine.Random.value * total;
            foreach (var p in pools)
            {
                if (p.clips == null || p.clips.Length == 0) continue;
                r -= p.weight;
                if (r <= 0 && p.weight > 0) return p;
            }
            return pools[0];
        }
    }
}
