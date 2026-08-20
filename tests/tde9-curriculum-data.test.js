"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const dataPath = path.resolve(__dirname, "..", "shared", "pilot", "tde9", "learning-outcomes-template.json");
const payload = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const outcomes = payload.learning_outcomes;

assert.equal(outcomes.length, 54);
assert.deepEqual(
  outcomes.reduce((counts, outcome) => {
    counts[outcome.theme] = (counts[outcome.theme] || 0) + 1;
    return counts;
  }, {}),
  {
    "1. Tema: Sözün İnceliği": 12,
    "2. Tema: Anlam Arayışı": 12,
    "3. Tema: Anlamın Yapı Taşları": 14,
    "4. Tema: Dilin Zenginliği": 16
  }
);

assert.equal(new Set(outcomes.map((outcome) => outcome.id)).size, outcomes.length);

const themeOneMeaning = outcomes.find((outcome) => outcome.id === "tema1-tde2-2");
assert.deepEqual(themeOneMeaning.processComponents.map((component) => component.code), [
  "TDE2.2.1", "TDE2.2.2", "TDE2.2.3", "TDE2.2.4", "TDE2.2.5"
]);
assert.equal(
  themeOneMeaning.processComponents[0].title,
  "Ön bilgilerle bağlantı kurar."
);
assert.match(themeOneMeaning.processComponents[3].indicators[0], /metnin konusunu, temasını, yardımcı ve ana düşüncesini/);
assert.match(themeOneMeaning.processComponents[4].indicators[0], /gerçek-kurgu, öznel-nesnel ifadeleri/);

const themeThreeListening = outcomes.find((outcome) => outcome.id === "tema3-tde1-1");
assert.equal(
  themeThreeListening.title,
  "“Anlamın Yapı Taşları” temasında ele alınan metinlerde dinleme/izlemeyi yönetebilme"
);

const revisedTitles = {
  "tema1-tde3-4": "Söyleyiş inceliğinin konuşmasına etkisiyle ilgili süreci değerlendirebilme",
  "tema1-tde4-4": "Edebî söyleyişin inceliğini yansıttığı yazısında yazma sürecini değerlendirebilme",
  "tema2-tde3-3": "Konusunu ana düşünce etrafında detaylandırdığı konuşmasında kural uygulayabilme",
  "tema2-tde3-4": "Konuşmasının içeriğinde kullandığı unsurların konuşmasına olan etkisine yönelik süreci değerlendirebilme",
  "tema2-tde4-4": "Beğeni ve eleştirilerini dile getirdiği yazısına yönelik yazma sürecini değerlendirebilme",
  "tema3-tde3-4": "Edebî metinlerdeki yapısal inceliklerin konuşmaya etkisine yönelik süreci değerlendirebilme",
  "tema3-tde4-4": "Yapısını incelikle ördüğü yazısına yönelik yazma sürecini değerlendirebilme",
  "tema4-tde1-4": "“Dilin Zenginliği” temasında ele alınan metinlerde dinleme/izleme sürecini değerlendirebilme",
  "tema4-tde2-4": "“Dilin Zenginliği” temasında ele alınan metinlere yönelik okuma sürecini değerlendirebilme",
  "tema4-tde3-4": "Kullandığı dil özelliklerinin konuşmasına etkisine yönelik süreci değerlendirebilme",
  "tema4-tde4-4": "Beğeni ve eleştirilerini dile getirdiği yazısına yönelik yazma sürecini değerlendirebilme"
};
for (const [id, title] of Object.entries(revisedTitles)) {
  assert.equal(outcomes.find((outcome) => outcome.id === id).title, title);
}

for (const outcome of outcomes) {
  assert.ok(outcome.id && outcome.theme && outcome.code && outcome.title && outcome.skill);
  const componentCodes = (outcome.processComponents || []).map((component) => component.code);
  assert.equal(new Set(componentCodes).size, componentCodes.length, `${outcome.id} süreç bileşeni kodları yinelenmemeli`);
  for (const component of outcome.processComponents || []) {
    assert.ok(component.title, `${outcome.id}/${component.code} kısa süreç başlığı bulunmalı`);
    assert.ok(
      Array.isArray(component.indicators) && component.indicators.length > 0,
      `${outcome.id}/${component.code} resmî ayrıntılı göstergeleri içermeli`
    );
  }
}

const expectedDetailedComponents = {
  "tema1-tde1-2": ["TDE1.2.1", "TDE1.2.2", "TDE1.2.3", "TDE1.2.4"],
  "tema2-tde1-2": ["TDE1.2.1", "TDE1.2.2", "TDE1.2.3", "TDE1.2.4", "TDE1.2.5", "TDE1.2.6"],
  "tema3-tde1-3": ["TDE1.3.1", "TDE1.3.2", "TDE1.3.3"],
  "tema4-tde1-4": ["TDE1.4.1", "TDE1.4.2"],
  "tema4-tde2-2": ["TDE2.2.1", "TDE2.2.2", "TDE2.2.3", "TDE2.2.4", "TDE2.2.5", "TDE2.2.6"],
  "tema3-tde3-2": ["TDE3.2.1", "TDE3.2.2", "TDE3.2.3", "TDE3.2.4", "TDE3.2.5", "TDE3.2.6", "TDE3.2.7", "TDE3.2.8", "TDE3.2.9"],
  "tema4-tde3-3": ["TDE3.3.1", "TDE3.3.2", "TDE3.3.3", "TDE3.3.4", "TDE3.3.5", "TDE3.3.6", "TDE3.3.7"],
  "tema3-tde4-3": ["TDE4.3.1", "TDE4.3.2", "TDE4.3.3", "TDE4.3.4", "TDE4.3.5", "TDE4.3.6", "TDE4.3.7", "TDE4.3.8"],
  "tema4-tde4-4": ["TDE4.4.1", "TDE4.4.2"]
};
for (const [id, codes] of Object.entries(expectedDetailedComponents)) {
  assert.deepEqual(
    outcomes.find((outcome) => outcome.id === id).processComponents.map((component) => component.code),
    codes,
    `${id} süreç bileşenleri resmî sırayı korumalı`
  );
}

for (const outcome of outcomes) {
  assert.ok(
    Array.isArray(outcome.processComponents) && outcome.processComponents.length > 0,
    `${outcome.id} süreç bileşenleri ayrıntılı tanımlanmalı`
  );
}

console.log("tde9-curriculum-data.test.js: all assertions passed");
