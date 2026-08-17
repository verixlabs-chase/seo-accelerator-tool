export function isLocationAllowanceEnforced(allowance) {
  return allowance?.plan?.location_allowance_enforced === true;
}

export function canActivateAnotherLocation(allowance) {
  if (!allowance?.plan) return false;
  if (!isLocationAllowanceEnforced(allowance)) return true;
  if (typeof allowance.plan.can_activate_location === "boolean") {
    return allowance.plan.can_activate_location;
  }
  return Number(allowance.plan.remaining_locations || 0) > 0;
}
