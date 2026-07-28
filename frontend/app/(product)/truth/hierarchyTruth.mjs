export function flattenBusinessLocations(hierarchy) {
  const subaccounts = Array.isArray(hierarchy?.subaccounts) ? hierarchy.subaccounts : [];
  const assigned = subaccounts.flatMap((subaccount) =>
    (Array.isArray(subaccount?.business_locations) ? subaccount.business_locations : []).map(
      (location) => ({
        ...location,
        subaccount_name: subaccount.name,
      }),
    ),
  );
  const unassigned = Array.isArray(hierarchy?.unassigned?.business_locations)
    ? hierarchy.unassigned.business_locations.map((location) => ({
        ...location,
        subaccount_name: "Unassigned",
      }))
    : [];
  return [...assigned, ...unassigned];
}

export function getHierarchyTruth(hierarchy) {
  const totals = hierarchy?.totals || {};
  const subaccounts = Number(totals.subaccounts || 0);
  const locations = Number(totals.business_locations || 0);
  const unassigned = Number(totals.unassigned_business_locations || 0);
  const integrityIssues = Number(totals.integrity_issues || 0);

  if (integrityIssues > 0) {
    return {
      label: "Needs repair",
      tone: "danger",
      summary: `${integrityIssues} hierarchy relationship${integrityIssues === 1 ? "" : "s"} need attention.`,
    };
  }
  if (unassigned > 0) {
    return {
      label: "Setup incomplete",
      tone: "warning",
      summary: `${unassigned} business location${unassigned === 1 ? "" : "s"} still need an account group.`,
    };
  }
  if (subaccounts === 0 || locations === 0) {
    return {
      label: "Setup needed",
      tone: "warning",
      summary: "Create an account group and its first business location.",
    };
  }
  return {
    label: "Structured",
    tone: "success",
    summary: `${locations} location${locations === 1 ? "" : "s"} organized across ${subaccounts} account group${subaccounts === 1 ? "" : "s"}.`,
  };
}
