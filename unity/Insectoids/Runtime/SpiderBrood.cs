using System;
using System.Collections.Generic;
using UnityEngine;

namespace Insectoids
{
    /// <summary>
    /// The broodmother's end of her Spawn clip. The clip squeezes an egg out of the spinnerets and sets it down under
    /// Socket_Spinneret; at that moment (event "Spawn", 3.0 s) the clip's egg shrinks away and this puts
    /// <see cref="spawnPrefab"/> (an egg prop, or a spiderling) on the ground under the socket, turned like the mother.
    /// Hook <see cref="Spawned"/> for gameplay (hatching, AI). Only in Play mode (<see cref="SpiderFx.CanSpawn"/>):
    /// animation events also fire in edit-mode previews.
    /// </summary>
    public class SpiderBrood : MonoBehaviour
    {
        [Tooltip("What the Spawn event puts down: SpiderEgg_Single, or Spider_Spiderling.")]
        public GameObject spawnPrefab;
        [Tooltip("Scale the spawned object with the mother's size roll (the egg in her clip is hers).")]
        public bool matchScale = true;
        [Tooltip("Oldest one goes when there would be more than this many (0 = no limit).")]
        public int maxAlive = 6;
        [Tooltip("Seconds before a spawned object is removed (0 = keep).")]
        public float lifetime = 30f;

        /// <summary>(mother, the new egg or spiderling).</summary>
        public event Action<SpiderBrood, GameObject> Spawned;

        public Transform Spinneret { get; private set; }
        readonly List<GameObject> alive = new List<GameObject>();

        void Awake()
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (t.name == "Socket_Spinneret") Spinneret = t;
        }

        /// <summary>Called by the clips' animation events (Bite, Spawn, Dead...).</summary>
        public void OnInsectEvent(string name)
        {
            if (name == "Spawn") Spawn();
        }

        /// <summary>Put one down now, under the spinnerets.</summary>
        public GameObject Spawn()
        {
            if (!SpiderFx.CanSpawn || spawnPrefab == null) return null;
            alive.RemoveAll(g => g == null);
            if (maxAlive > 0 && alive.Count >= maxAlive)
            {
                Destroy(alive[0]);
                alive.RemoveAt(0);
            }
            var p = Spinneret != null ? Spinneret.position : transform.position - transform.forward;
            float ground = transform.position.y;                // no collider below: the mother's feet level
            bool found = false;
            foreach (var hit in Physics.RaycastAll(p + Vector3.up * 0.5f, Vector3.down, 6f, ~0, QueryTriggerInteraction.Ignore))
            {
                if (hit.transform.IsChildOf(transform) || (found && hit.point.y <= ground)) continue;
                ground = hit.point.y;
                found = true;
            }
            var go = Instantiate(spawnPrefab, new Vector3(p.x, ground, p.z), Quaternion.Euler(0, transform.eulerAngles.y - 12f, 0));
            if (matchScale) go.transform.localScale = Vector3.Scale(go.transform.localScale, Vector3.one * transform.lossyScale.x);
            alive.Add(go);
            if (lifetime > 0) Destroy(go, lifetime);
            Spawned?.Invoke(this, go);
            return go;
        }
    }
}
