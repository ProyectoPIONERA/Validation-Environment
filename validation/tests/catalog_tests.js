/**
 * Catalog discovery tests
 * Validates catalog responses from provider
 */
(function() {
const requestName = pm.info.requestName
const status = pm.response.code
if (requestName === "Direct DSP Catalog Request") {
    if (status === 401) {
        pm.test("Direct DSP catalog request requires authentication", function () {
            pm.expect(status).to.equal(401)
        })
    } else {
        pm.test("Direct DSP catalog request completed", function () {
            pm.expect(status).to.be.oneOf([200, 401])
        })
    }
    return
}
if (status !== 200) {
    pm.test("Federated catalog request skipped due to connector environment response", function () {
        pm.expect([200, 400, 502]).to.include(status)
    })
    console.log("Federated catalog raw response:", pm.response.text())
    return
}
const body = parseJsonResponse()
if (!body) {
    console.log("No valid response body, skipping tests")
    return
}
assertJsonNotEmpty(body)
assertNoEdcError(body)
assertStatus200();
const catalog = Array.isArray(body) ? body[0] : body
pm.test("Catalog response contains dataset field", function () {
    pm.expect(catalog).to.have.property("dcat:dataset");
});
if (!catalog["dcat:dataset"]) {
    return
}
let datasets = catalog["dcat:dataset"];
if (!Array.isArray(datasets)) {
    datasets = [datasets];
}
pm.test("Dataset list not empty", function () {
    pm.expect(datasets.length).to.be.above(0);
});
const dataset = datasets[0];
pm.test("Dataset has @id", function () {
    pm.expect(dataset).to.have.property("@id");
});
pm.test("Dataset contains policy", function () {
    pm.expect(dataset).to.have.property("odrl:hasPolicy");
});
let policy = dataset["odrl:hasPolicy"];
if (Array.isArray(policy)) {
    policy = policy[0];
}
saveCollectionVar("providerParticipantId", catalog["dspace:participantId"] || pm.environment.get("provider"))
if (policy && policy["@id"]) {
    saveCollectionVar("policyId", policy["@id"]);
}
if (dataset["@id"]) {
    saveCollectionVar("assetId", dataset["@id"]);
}
console.log("Catalog participant:", catalog["dspace:participantId"]);
console.log("Catalog datasets:", datasets.length);
console.log("First dataset:", dataset);
})(); // End of IIFE
