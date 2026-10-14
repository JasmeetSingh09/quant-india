// A factor that could not be measured returns score 0, confidence 0 and a
// reason. The 0 exists so the composite has something to weight; it is not a
// measurement, and printing it as "+0.0 pts" told users a stock had flat
// momentum when the source simply had too little price history (172 stocks on
// 2026-10-14). Same test as backend model_config.is_refusal: a reason AND zero
// confidence. Value's "-0.5 at confidence 0.6" for distress is a judgement,
// not a refusal, and stays a number.
export function isRefused(f) {
  if (!f || typeof f !== 'object' || !('reason' in f)) return false
  return Number(f.confidence || 0) === 0
}
