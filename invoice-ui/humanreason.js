/**
 * Generate human-readable context for each invoice result.
 * Replaces technical messages like "score gap 0.000 < threshold, LLM inconclusive"
 * with plain language explanations for ops/finance teams.
 */

export function getHumanReason(result) {
  const { status, score_gap, reason, top_candidates } = result;

  if (status === "NO_PLATE") {
    return {
      short: "No truck plate found on this invoice.",
      detail:
        "The invoice is missing a truck plate number, which is required to link it to a delivery. It needs to be matched manually or escalated to the carrier.",
    };
  }

  if (status === "NO_MATCH") {
    if (reason?.includes("date")) {
      return {
        short: "Invoice date falls outside the expected delivery window.",
        detail:
          "The invoice was issued more than 1 day before pickup or after dropoff. This may indicate a data entry delay or a delivery from a different batch.",
      };
    }
    return {
      short: "No matching delivery found for this truck.",
      detail:
        "The truck plate on this invoice does not correspond to any delivery in the current dataset. It likely belongs to a shipment outside this batch.",
    };
  }

  if (status === "AUTO_MATCH") {
    const top = top_candidates?.[0];
    const name = top?.delivery_name || `Delivery #${top?.delivery_id}`;
    const addr = top?.delivery_description || "";
    return {
      short: `Automatically matched to ${name}.`,
      detail: addr
        ? `Address and weight signals confidently point to ${name} (${addr}). No manual review needed.`
        : `Address and weight signals confidently point to ${name}. No manual review needed.`,
    };
  }

  if (status === "LLM_MATCH") {
    const top = top_candidates?.[0];
    const name = top?.delivery_name || `Delivery #${top?.delivery_id}`;
    return {
      short: `Matched by AI to ${name}.`,
      detail: `The address was ambiguous for rule-based scoring, so AI was used to interpret the delivery location semantically. Confidence is sufficient for auto-assignment, but you may want to spot-check.`,
    };
  }

  if (status === "MANUAL_REVIEW") {
    // Gap = 0 → identical scores, truly unresolvable
    if (score_gap === 0 || score_gap < 0.01) {
      const candidates = top_candidates || [];
      if (candidates.length >= 2) {
        return {
          short: "Multiple deliveries are equally likely — cannot auto-assign.",
          detail:
            "Two or more deliveries share the same truck, date range, and destination area. The invoice delivery address points to a transit warehouse rather than the final dropoff point, making it impossible to determine the correct delivery automatically. Please review the invoice alongside the delivery list.",
        };
      }
      return {
        short: "Could not determine the correct delivery automatically.",
        detail:
          "The available data does not provide enough signal to assign this invoice confidently. Manual review is required.",
      };
    }

    // Small gap → close but not close enough
    if (score_gap < 0.1) {
      const top = top_candidates?.[0];
      const second = top_candidates?.[1];
      const name1 = top?.delivery_name || `Delivery #${top?.delivery_id}`;
      const name2 = second?.delivery_name || `Delivery #${second?.delivery_id}`;
      return {
        short: `Close call between ${name1} and ${name2}.`,
        detail: `The invoice address is not specific enough to distinguish between these two deliveries with confidence. ${name1} is the best candidate, but ${name2} scored similarly. Please verify the delivery address on the original invoice document.`,
      };
    }

    // Moderate gap → LLM couldn't resolve
    return {
      short: "AI could not determine the match with enough confidence.",
      detail:
        "The invoice address contains ambiguous or incomplete location information. Automatic matching was attempted but the result was not reliable enough to auto-assign. Please compare the invoice delivery address with the candidate deliveries below.",
    };
  }

  return {
    short: "Status unknown.",
    detail: reason || "No additional context available.",
  };
}
