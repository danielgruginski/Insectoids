using UnityEngine;

namespace Insectoids
{
    /// <summary>
    /// Viewer for the insectoid test scene: orbit camera with colony / mid / close presets (right-drag orbits, scroll
    /// zooms), labels over the creatures, time scale, reshuffle, re-roll looks, and buttons that make every spider do
    /// one thing at once (web spit, bite, threat...). IMGUI only, so it works with either input system.
    /// </summary>
    [RequireComponent(typeof(Camera))]
    public class InsectTestUI : MonoBehaviour
    {
        public Vector3 focus = new Vector3(0, 0.6f, 0);
        public float distance = 22f, pitch = 40f, yaw = 200f;
        public bool orbit = true;
        public bool labels = true;

        Camera cam;
        float timeScale = 1f;
        bool looksLabels;
        readonly System.Collections.Generic.List<string> actions = new System.Collections.Generic.List<string>();
        int actionsFor = -1;

        /// <summary>Every pool name in the scene's animation sets (spider and wasp alike), GetUp left out.</summary>
        System.Collections.Generic.List<string> Actions
        {
            get
            {
                if (actionsFor == InsectRandomAnimator.All.Count) return actions;
                actions.Clear();
                foreach (var c in InsectRandomAnimator.All)
                    if (c.set != null)
                        foreach (var p in c.set.pools)
                            if (p.name != "GetUp" && p.name != "Idle" && !actions.Contains(p.name)) actions.Add(p.name);
                actionsFor = InsectRandomAnimator.All.Count;
                return actions;
            }
        }

        void Awake()
        {
            cam = GetComponent<Camera>();
            Application.runInBackground = true;          // keep ticking while the editor window is not focused
        }

        void LateUpdate()
        {
            if (orbit) yaw += 4f * Time.unscaledDeltaTime;
            var rot = Quaternion.Euler(pitch, yaw, 0);
            transform.SetPositionAndRotation(focus + rot * new Vector3(0, 0, -distance), rot);
        }

        void Preset(float d, float p, float fov)
        {
            distance = d;
            pitch = p;
            cam.fieldOfView = fov;
        }

        void OnGUI()
        {
            var e = Event.current;
            if (e.type == EventType.MouseDrag && e.button == 1)
            {
                yaw += e.delta.x * 0.3f;
                pitch = Mathf.Clamp(pitch + e.delta.y * 0.2f, 5f, 85f);
            }
            if (e.type == EventType.ScrollWheel)
                distance = Mathf.Clamp(distance * (1f + e.delta.y * 0.05f), 2f, 90f);

            GUILayout.BeginArea(new Rect(10, 10, 300, 520), GUI.skin.box);
            GUILayout.Label($"Creatures: {InsectRandomAnimator.All.Count}   webs: {SpiderWebSnare.All.Count}");
            GUILayout.Label("right-drag orbit, scroll zoom");
            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Colony 40m")) Preset(40f, 50f, 30f);
            if (GUILayout.Button("Mid 18m")) Preset(18f, 38f, 35f);
            if (GUILayout.Button("Close 7m")) Preset(7f, 16f, 40f);
            GUILayout.EndHorizontal();
            orbit = GUILayout.Toggle(orbit, "Slow orbit");
            labels = GUILayout.Toggle(labels, "Show labels");
            if (labels) looksLabels = GUILayout.Toggle(looksLabels, "   labels show looks (not clips)");
            GUILayout.Label($"Time scale {timeScale:F2}");
            timeScale = GUILayout.HorizontalSlider(timeScale, 0.1f, 2f);
            Time.timeScale = timeScale;
            if (GUILayout.Button("Reshuffle animations"))
                foreach (var c in InsectRandomAnimator.All) c.Restart();
            if (GUILayout.Button("Re-roll looks"))
                foreach (var c in InsectRandomAnimator.All)
                    if (c.TryGetComponent<InsectAppearance>(out var look)) look.Reroll();
            GUILayout.Label("Every creature that has it, now:");
            var acts = Actions;
            for (int i = 0; i < acts.Count; i += 3)
            {
                GUILayout.BeginHorizontal();
                for (int j = i; j < Mathf.Min(i + 3, acts.Count); j++)
                    if (GUILayout.Button(acts[j]))
                        foreach (var c in InsectRandomAnimator.All) c.PlayPool(acts[j]);
                GUILayout.EndHorizontal();
            }
            GUILayout.EndArea();

            if (!labels) return;
            var style = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontSize = 11, wordWrap = true };
            foreach (var c in InsectRandomAnimator.All)
            {
                var sp = cam.WorldToScreenPoint(c.transform.position + Vector3.up * c.labelHeight * c.transform.lossyScale.y);
                if (sp.z < 0) continue;
                string text = c.CurrentClip;
                if (looksLabels && c.TryGetComponent<InsectAppearance>(out var look)) text = look.Summary;
                var r = new Rect(sp.x - 150, Screen.height - sp.y - 20, 300, 40);
                GUI.color = Color.black;
                GUI.Label(new Rect(r.x + 1, r.y + 1, r.width, r.height), text, style);
                GUI.color = Color.white;
                GUI.Label(r, text, style);
            }
        }
    }
}
