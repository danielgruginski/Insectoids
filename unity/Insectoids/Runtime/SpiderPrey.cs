using System.Collections.Generic;
using UnityEngine;

namespace Insectoids
{
    /// <summary>Marks something a spider may spit at (see <see cref="SpiderCombat.autoTarget"/>).</summary>
    public class SpiderPrey : MonoBehaviour
    {
        public static readonly List<SpiderPrey> All = new List<SpiderPrey>();
        void OnEnable() => All.Add(this);
        void OnDisable() => All.Remove(this);
    }
}
