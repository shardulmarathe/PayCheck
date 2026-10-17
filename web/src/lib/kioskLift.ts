/** 0 while the problem section is on screen, then 0→1 as the replay arrives. */
export function replayLiftProgress(): number {
  const replay = document.querySelector(".replay-section")?.getBoundingClientRect();
  if (!replay) return 0;
  const vh = window.innerHeight;
  const problem = document.getElementById("problem")?.getBoundingClientRect();
  const gate = Math.min(72, vh * 0.08);
  if (problem && problem.bottom > gate) return 0;
  const gap = problem ? replay.top - problem.bottom : 0;
  const start = gate + gap;
  const end = start - Math.min(420, vh * 0.46);
  return Math.min(1, Math.max(0, (start - replay.top) / (start - end)));
}
