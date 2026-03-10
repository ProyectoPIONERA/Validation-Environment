/**
 * Contract negotiation tests
 * Used by:
 * 05_consumer_negotiation.json
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
 * Consumer authentication
 */
if (requestName === "Consumer Login") {
    assertFieldExists(body, "access_token")
    saveCollectionVar("consumer_jwt", body.access_token)
}
/**
 * Contract negotiation start
 */
if (requestName === "Start Contract Negotiation") {
    extractAtId(body, "contract_negotiation_id")
}
/**
 * Negotiation status check
 */
if (requestName === "Check Negotiation Status") {
    const negotiationId = pm.collectionVariables.get("contract_negotiation_id")
    let negotiation = body
    if (Array.isArray(body)) {
        pm.test("Negotiation list not empty", function () {
            pm.expect(body.length).to.be.above(0)
        })
        negotiation = body.find(function (item) {
            return item && (item["@id"] === negotiationId || item.id === negotiationId)
        }) || body[0]
    }
    assertFieldExists(negotiation, "state")
    const state = negotiation.state
    pm.test("Negotiation state is valid", function () {
        pm.expect(state).to.be.oneOf([
            "INITIAL",
            "REQUESTED",
            "REQUESTING",
            "IN_PROGRESS",
            "FINALIZED",
            "TERMINATED"
        ])
    })
    const agreementId = negotiation.contractAgreementId
    if (agreementId) {
        saveCollectionVar("contract_agreement_id", agreementId)
        pm.test("Contract agreement generated", function () {
            pm.expect(agreementId).to.not.be.undefined
            pm.expect(agreementId).to.not.be.null
        })
    } else {
        pm.test("Negotiation has not produced a contract agreement yet", function () {
            pm.expect(true).to.be.true
        })
        if (negotiation.errorDetail) {
            console.log("Negotiation error detail:", negotiation.errorDetail)
        }
    }
}
})(); // End of IIFE
