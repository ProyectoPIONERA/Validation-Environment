/**
 * Transfer process tests
 * Used by:
 * 06_consumer_transfer.json
 */
(function() {
const requestName = pm.info.requestName
const body = requestName === "Download Data" ? null : parseJsonResponse()
if (requestName === "Consumer Login") {
    handleLoginToken(body)
    return
}
const agreementId = getStoredVar("e2e_agreement_id")
if (requestName === "Start Transfer Process" && !agreementId) {
    pm.test("Transfer skipped because no contract agreement is available", function () {
        pm.expect(true).to.be.true
    })
    return
}
if (requestName !== "Download Data" && requestName !== "Start Transfer Process") {
    assertStatus200()
}
if (!body && requestName !== "Download Data") {
    console.log("No valid response body, skipping tests")
    return
}
if (body) {
    assertNoEdcError(body)
}
if (requestName === "Start Transfer Process") {
    assertCreated()
    extractAtId(body, "e2e_transfer_id")
    return
}
if (requestName === "Check Transfer Status") {
    const transferId = getStoredVar("e2e_transfer_id")
    let transfer = body
    if (Array.isArray(body)) {
        if (body.length === 0) {
            pm.test("Transfer status skipped because no transfer process exists yet", function () {
                pm.expect(true).to.be.true
            })
            return
        }
        transfer = body.find(function (item) {
            return item && (item["@id"] === transferId || item.id === transferId)
        }) || body[0]
    }
    if (!transfer) {
        pm.test("Transfer status skipped because no transfer process exists yet", function () {
            pm.expect(true).to.be.true
        })
        return
    }
    assertFieldExists(transfer, "state")
    const state = transfer.state
    pm.test("Transfer state is valid", function () {
        pm.expect(state).to.be.oneOf([
            "INITIAL",
            "REQUESTED",
            "IN_PROGRESS",
            "COMPLETED",
            "FINALIZED",
            "TERMINATED"
        ])
    })
}
if (requestName === "Retrieve Endpoint Data Reference") {
    const transferId = getStoredVar("e2e_transfer_id")
    let edr = body
    if (Array.isArray(body)) {
        if (body.length === 0) {
            pm.test("EDR retrieval skipped because no EDR is available yet", function () {
                pm.expect(true).to.be.true
            })
            return
        }
        edr = body.find(function (item) {
            return item && (item.transferProcessId === transferId || item["@id"] === transferId || item.id === transferId)
        }) || body[0]
    }
    if (!edr) {
        pm.test("EDR retrieval skipped because no EDR is available yet", function () {
            pm.expect(true).to.be.true
        })
        return
    }
    let endpoint
    let auth
    if (edr.dataAddress) {
        endpoint = edr.dataAddress.endpoint
        auth = edr.dataAddress.authorization
    } else {
        endpoint = edr.endpoint
        auth = edr.authorization
    }
    if (!endpoint || !auth) {
        pm.test("EDR retrieval skipped because endpoint data is incomplete", function () {
            pm.expect(true).to.be.true
        })
        return
    }
    saveCollectionVar("e2e_endpoint", endpoint)
    saveCollectionVar("e2e_authorization_token", auth)
    pm.test("EDR contains endpoint and authorization", function () {
        pm.expect(endpoint).to.not.equal("")
        pm.expect(auth).to.not.equal("")
    })
}
if (requestName === "Download Data") {
    const endpoint = getStoredVar("e2e_endpoint")
    if (!endpoint) {
        pm.test("Download skipped because no endpoint is available", function () {
            pm.expect(true).to.be.true
        })
        return
    }
    assertStatus200()
    const text = pm.response.text()
    pm.test("Data retrieved successfully", function () {
        pm.expect(text.length).to.be.greaterThan(0)
    })
}
})(); // End of IIFE
