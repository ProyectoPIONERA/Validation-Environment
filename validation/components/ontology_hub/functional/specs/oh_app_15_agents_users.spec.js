// Excel traceability: Ontology Hub cases 15, 16, 17 and 18.
// Normalization note for case 15: Atlas/Docker activation steps are intentionally excluded;
// if the application does not activate or propagate the new user internally, the test fails.
const { test } = require("../../ui/fixtures");
const {
  assertCreateUserControl,
  createAgent,
  createUserForAgent,
  deleteAgentFromPublicDetail,
  editAgentFromPublicDetail,
  deleteRunState,
  loadRunState,
  promoteUserToAdmin,
  reviewPendingUser,
  runIndexAllFromEdition,
  saveRunState,
  signInToEdition,
  signOut,
} = require("../support/excel-flows");

test.setTimeout(120000);

const AGENT_USER_STATE_KEY = "oh-app-15-agent-user";

function buildIdentity() {
  return {
    agentName: "Testing User",
    updatedAgentName: "Testing User Admin",
    prefUri: "http://ontology-hub-demo.pionera.oeg.fi.upm.es/testingUser",
    email: "testing@myemail.com",
    password: "testing123",
  };
}

test("OH-APP-15: create agent and user, then verify + USER is hidden", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const identity = buildIdentity();
  await signInToEdition(page, ontologyHubRuntime);
  await page.goto(`${ontologyHubRuntime.baseUrl}/edition/users`, { waitUntil: "domcontentloaded" });

  const agent = await createAgent(page, ontologyHubRuntime, {
    name: identity.agentName,
    prefUri: identity.prefUri,
    type: "person",
  });
  const user = await createUserForAgent(page, ontologyHubRuntime, {
    agentName: identity.agentName,
    email: identity.email,
    password: identity.password,
  });
  await reviewPendingUser(page, ontologyHubRuntime, user);
  await runIndexAllFromEdition(page, ontologyHubRuntime);
  saveRunState(AGENT_USER_STATE_KEY, {
    ...identity,
    currentAgentName: identity.agentName,
  });

  await signOut(page, ontologyHubRuntime);
  await signInToEdition(page, ontologyHubRuntime, {
    email: user.email,
    password: user.password,
  });
  await page.goto(`${ontologyHubRuntime.baseUrl}/edition`, { waitUntil: "domcontentloaded" });
  await assertCreateUserControl(page, false);
  await captureStep(page, "15-created-user-limited-edition");
  await signOut(page, ontologyHubRuntime);

  await attachJson("15-create-agent-user-report", {
    agent,
    user,
  });
});

test("OH-APP-16: edit agent from the public detail page", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const identity = loadRunState(AGENT_USER_STATE_KEY);
  await editAgentFromPublicDetail(page, ontologyHubRuntime, identity.currentAgentName, identity.updatedAgentName);
  await captureStep(page, "16-agent-edited");
  await signOut(page, ontologyHubRuntime);
  saveRunState(AGENT_USER_STATE_KEY, {
    ...identity,
    currentAgentName: identity.updatedAgentName,
  });

  await attachJson("16-edit-agent-report", {
    initialName: identity.currentAgentName,
    updatedName: identity.updatedAgentName,
  });
});

test("OH-APP-17: promote user to admin and verify + USER appears", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const identity = loadRunState(AGENT_USER_STATE_KEY);
  await signInToEdition(page, ontologyHubRuntime);
  await page.goto(`${ontologyHubRuntime.baseUrl}/edition/users`, { waitUntil: "domcontentloaded" });

  await promoteUserToAdmin(page, ontologyHubRuntime, {
    email: identity.email,
  });
  await signOut(page, ontologyHubRuntime);

  await signInToEdition(page, ontologyHubRuntime, {
    email: identity.email,
    password: identity.password,
  });
  await page.goto(`${ontologyHubRuntime.baseUrl}/edition`, { waitUntil: "domcontentloaded" });
  await assertCreateUserControl(page, true);
  await captureStep(page, "17-user-promoted-admin");
  await signOut(page, ontologyHubRuntime);

  await attachJson("17-promote-user-report", {
    agentName: identity.currentAgentName,
    email: identity.email,
  });
});

test("OH-APP-18: delete agent from the public detail page", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const identity = loadRunState(AGENT_USER_STATE_KEY);

  await deleteAgentFromPublicDetail(page, ontologyHubRuntime, identity.currentAgentName);
  await captureStep(page, "18-agent-deleted");
  await signOut(page, ontologyHubRuntime);
  deleteRunState(AGENT_USER_STATE_KEY);

  await attachJson("18-delete-agent-report", {
    deletedName: identity.currentAgentName,
  });
});
