using UnityEngine;

namespace Insectoids
{
    /// <summary>
    /// Rolls a look for each creature in Awake: a skin (the material in <see cref="materialSlot"/>; list one twice to make
    /// it twice as likely) and a size. Each creature is already one skinned mesh, so this costs nothing at runtime:
    /// creatures with the same skin share materials and batch. <see cref="Reroll"/> rolls again; set <see cref="seed"/>
    /// for a fixed look.
    /// </summary>
    public class InsectAppearance : MonoBehaviour
    {
        public Material[] skins;
        [Tooltip("Which material of the skinned mesh the skins replace (the wasp's wings are slot 1).")]
        public int materialSlot;
        [Tooltip("Uniform scale range.")]
        public Vector2 scale = new Vector2(0.85f, 1.2f);
        [Tooltip("0 = random every time.")]
        public int seed;

        public string Summary { get; private set; } = "";

        void Awake() => Roll(seed != 0 ? seed : Random.Range(1, int.MaxValue));

        public void Reroll() => Roll(Random.Range(1, int.MaxValue));

        void Roll(int s)
        {
            var rng = new System.Random(s);
            var smr = GetComponentInChildren<SkinnedMeshRenderer>();
            string skin = "";
            if (smr != null && skins != null && skins.Length > 0)
            {
                var m = skins[rng.Next(skins.Length)];
                var mats = smr.sharedMaterials;
                if (m != null && materialSlot < mats.Length)
                {
                    mats[materialSlot] = m;
                    smr.sharedMaterials = mats;
                    var parts = m.name.Split('_');
                    skin = parts.Length > 2 ? parts[2] : "Base";
                }
            }
            float k = Mathf.Lerp(scale.x, scale.y, (float)rng.NextDouble());
            transform.localScale = Vector3.one * k;
            Summary = $"{skin} x{k:0.00}";
        }
    }
}
