// Display-only fallback while an active local service still has older price cards.
const prices: Record<string, [number, number, number, number]> = {
  "gpt-6-luna": [0.1, 0.5, 0.01, 0.125],
  "gpt-6-sol": [2, 10, 0.2, 2.5],
};

export function currentModelReferenceCost(
  model: string,
  usage: Record<string, any>,
) {
  const rate = prices[model];
  const input = usage?.input_tokens;
  const output = usage?.output_tokens;
  if (
    !rate ||
    !Number.isSafeInteger(input) ||
    !Number.isSafeInteger(output) ||
    input < 0 ||
    output < 0 ||
    !usage.reported_calls
  )
    return null;
  const cached =
    Number.isSafeInteger(usage.cached_input_tokens) &&
    usage.cached_input_tokens > 0
      ? usage.cached_input_tokens
      : 0;
  const written =
    Number.isSafeInteger(usage.cache_write_tokens) &&
    usage.cache_write_tokens > 0
      ? usage.cache_write_tokens
      : 0;
  const [inputRate, outputRate, cachedRate, writeRate] = rate;
  const lower =
    (Math.max(0, input - cached - written) * inputRate +
      cached * cachedRate +
      written * writeRate +
      output * outputRate) /
    1e6;
  const upper =
    (input * inputRate +
      cached * cachedRate +
      written * writeRate +
      output * outputRate) /
    1e6;
  return {
    amount: String(lower),
    amount_range: [String(lower), String(upper)],
    currency: "USD",
    source: "https://developers.openai.com/api/docs/pricing",
    verified_on: "2026-09-23",
    display_fallback: true,
  };
}
