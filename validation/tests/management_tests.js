/**
 * Management API tests
 * Used by:
 * 02_connector_management_api.json
 */
(function() {
assertStatus200()
const body = parseJsonResponse()
if (!body) {
    console.log("No valid response body, skipping tests")
    return
}
assertNoEdcError(body)
/**
 * Detect which request is running
 */
const requestName = pm.info.requestName
/**
 * Provider Login
 */
if (requestName === "Provider Login") {
    assertFieldExists(body, "access_token")
    saveCollectionVar("provider_jwt", body.access_token)
}
/**
 * Create Asset
 */
if (requestName === "Create Asset") {
    assertCreated()
    extractAtId(body, "asset_id")
}
/**
 * List Assets
 */
if (requestName === "List Assets") {
    const assetId = pm.collectionVariables.get("asset_id")
    assertNotEmpty(assetId, "asset_id")
    const text = responseText()
    pm.test("Asset appears in asset list", function () {
        pm.expect(text).to.include(assetId)
    })
}
/**
 * Create Policy
 */
if (requestName === "Create Policy") {
    assertCreated()
    extractAtId(body, "policy_id")
}
/**
 * List Policies
 */
if (requestName === "List Policies") {
    const policyId = pm.collectionVariables.get("policy_id")
    assertNotEmpty(policyId, "policy_id")
    const text = responseText()
    pm.test("Policy appears in policy list", function () {
        pm.expect(text).to.include(policyId)
    })
}
/**
 * Create Contract Definition
 */
if (requestName === "Create Contract Definition") {
    assertCreated()
    extractAtId(body, "contract_definition_id")
}
/**
 * List Contract Definitions
 */
if (requestName === "List Contract Definitions") {
    const contractId = pm.collectionVariables.get("contract_definition_id")
    assertNotEmpty(contractId, "contract_definition_id")
    const text = responseText()
    pm.test("Contract definition appears in list", function () {
        pm.expect(text).to.include(contractId)
    })
}
})(); // End of IIFE
