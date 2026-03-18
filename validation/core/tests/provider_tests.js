/**
 * Provider setup tests
 * Used by:
 * 03_provider_setup.json
 */
(function() {
const requestName = pm.info.requestName
const body = parseJsonResponse()

if (requestName === "Provider Login") {
    assertStatus200()
    if (!body) {
        return
    }
    assertFieldExists(body, "access_token")
    saveCollectionVar("provider_jwt", body.access_token)

    const suffix = String(Date.now())
    saveCollectionVar("e2e_suffix", suffix)
    saveCollectionVar("e2e_asset_id", `asset-e2e-${suffix}`)
    saveCollectionVar("e2e_policy_id", `policy-e2e-${suffix}`)
    saveCollectionVar("e2e_contract_definition_id", `contract-e2e-${suffix}`)
    return
}

if (!body) {
    console.log("No valid response body, skipping tests")
    return
}

assertStatus200()
assertNoEdcError(body)

if (requestName === "Create E2E Asset") {
    assertCreated()
    extractAtId(body, "e2e_asset_id")
    return
}

if (requestName === "List E2E Assets") {
    const assetId = pm.collectionVariables.get("e2e_asset_id")
    assertNotEmpty(assetId, "e2e_asset_id")
    assertContains(responseText(), assetId, "E2E asset appears in asset list")
    return
}

if (requestName === "Create E2E Policy") {
    assertCreated()
    extractAtId(body, "e2e_policy_id")
    return
}

if (requestName === "List E2E Policies") {
    const policyId = pm.collectionVariables.get("e2e_policy_id")
    assertNotEmpty(policyId, "e2e_policy_id")
    assertContains(responseText(), policyId, "E2E policy appears in policy list")
    return
}

if (requestName === "Create E2E Contract Definition") {
    assertCreated()
    extractAtId(body, "e2e_contract_definition_id")
    return
}

if (requestName === "List E2E Contract Definitions") {
    const contractId = pm.collectionVariables.get("e2e_contract_definition_id")
    assertNotEmpty(contractId, "e2e_contract_definition_id")
    assertContains(responseText(), contractId, "E2E contract definition appears in list")
}
})(); // End of IIFE
