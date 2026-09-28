// Distance correction fitted from the calibration table: a piecewise-linear map
// from the anchor's reading to the tape-measured distance (both in cm). It is
// only valid for the antenna delay it was measured with.

function correctDistance(correction, cm, delay) {
  const points = correction && correction.points;
  if (!points || points.length < 2 || correction.delay !== delay) return cm;
  const first = points[0], last = points[points.length - 1];
  // Outside the measured range, keep the nearest point's offset.
  if (cm <= first[0]) return cm + first[1] - first[0];
  if (cm >= last[0]) return cm + last[1] - last[0];
  for (let i = 1; i < points.length; i++) {
    if (cm <= points[i][0]) {
      const [m0, a0] = points[i - 1], [m1, a1] = points[i];
      return a0 + (cm - m0) / (m1 - m0) * (a1 - a0);
    }
  }
  return cm;
}

async function loadCorrection() {
  try {
    const response = await fetch('/api/correction', {cache: 'no-store'});
    return response.ok ? await response.json() : null;
  } catch (_) {
    return null;
  }
}
