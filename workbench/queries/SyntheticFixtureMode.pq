// Parameter. Mirrors the Python detector flag --synthetic-fixtures.
//   false (DEFAULT, real-data classification): unexplained coverage gaps are COVERAGE_UNEXPLAINED and actionable;
//                                              rejected inputs are actionable.
//   true  (synthetic fixture sample only):      unexplained gaps are COVERAGE_FIXTURE_LIMITED and not actionable;
//                                              deliberately rejected inputs are not actionable.
// The approved golden findings describe the SYNTHETIC sample, so set this to true ONLY to verify against them.
false meta [IsParameterQuery = true, Type = "Logical", IsParameterQueryRequired = true]
