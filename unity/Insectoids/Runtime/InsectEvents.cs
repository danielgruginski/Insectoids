using System;
using UnityEngine;

namespace Insectoids
{
    /// <summary>
    /// Receives the clips' animation events (<c>OnInsectEvent(name)</c>: Sting, Dead...) and raises
    /// <see cref="EventFired"/>; hook damage and sound there. The spider's <see cref="SpiderCombat"/> does the same and
    /// adds the web spit.
    /// </summary>
    public class InsectEvents : MonoBehaviour
    {
        public event Action<InsectEvents, string> EventFired;
        public void OnInsectEvent(string name) => EventFired?.Invoke(this, name);
    }
}
