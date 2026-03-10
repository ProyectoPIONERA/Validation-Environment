/**
 * Provider setup tests
 * Used by:
 * 03_provider_setup.json
 */
(function() {
assertStatus200()
const body = parseJsonResponse()
if (!body) {
    console.log("No valid response body, skipping tests")
    return
}
assertNoEdcError(body)
const requestName = pm.info.requestName
/**
 * Provider authentication
 */
if (requestName === "Provider Login") {
    assertFieldExists(body, "access_token")
    saveCollectionVar("provider_jwt", body.access_token)
}
/**
 * Verify Asset Exists
 */
if (requestName === "Verify Asset Exists") {
    pm.test("Asset list returned", function () {
        pm.expect(Array.isArray(body)).to.be.true
    })
    pm.test("Asset list not empty", function () {
        pm.expect(body.length).to.be.above(0)
    })
    pm.test("Asset test entity exists", function () {
        pm.expect(responseText()).to.include("asset-test")
    })
}
/**
 * Verify Policy Exists
 */
if (requestName === "Verify Policy Exists") {
    pm.test("Policy list returned", function () {
        pm.expect(Array.isArray(body)).to.be.true
    })
    pm.test("Policy list not empty", function () {
        pm.expect(body.length).to.be.above(0)
    })
    pm.test("Policy test entity exists", function () {
        pm.expect(responseText()).to.include("policy-test")
    })
}
/**
 * Verify Contract Definition Exists
 */
if (requestName === "Verify Contract Definition Exists") {
    pm.test("Contract definition list returned", function () {
        pm.expect(Array.isArray(body)).to.be.true
    })
    pm.test("Contract definition list not empty", function () {
        pm.expect(body.length).to.be.above(0)
    })
    pm.test("Contract definition test entity exists", function () {
        pm.expect(responseText()).to.include("contract-test")
    })
}
})(); // End of IIFE
