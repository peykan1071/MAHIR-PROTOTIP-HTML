"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const dataPath = path.resolve(__dirname, "..", "shared", "pilot", "tde9", "learning-outcomes-template.json");
const payload = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const outcomes = payload.learning_outcomes;

assert.equal(
  payload.source.program,
  "Ortaöğretim Türk Dili ve Edebiyatı Dersi Öğretim Programı (Hazırlık, 9, 10, 11 ve 12. Sınıflar) - Türkiye Yüzyılı Maarif Modeli"
);

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
  "“Sözün İnceliği” temasında ele alınan metinlerden hareketle edebiyatın güzel sanatlarla ve diğer disiplinlerle ilişkisini ön bilgileriyle bağlantı kurarak belirler."
);
assert.match(themeOneMeaning.processComponents[3].title, /metnin konusunu, temasını, yardımcı ve ana düşüncesini/);
assert.match(themeOneMeaning.processComponents[4].title, /gerçek-kurgu, öznel-nesnel ifadeleri/);

const themeThreeListening = outcomes.find((outcome) => outcome.id === "tema3-tde1-1");
assert.equal(
  themeThreeListening.title,
  "“Anlamın Yapı Taşları” temasında ele alınan metinlerde dinleme/izlemeyi yönetebilme"
);

const revisedTitles = {
  "tema1-tde3-4": "Söyleyiş inceliğinin konuşmasına etkisini yansıtabilme",
  "tema1-tde4-4": "Edebî söyleyişin inceliğini yansıttığı yazısına yönelik değerlendirmelerini yansıtabilme",
  "tema2-tde3-3": "Konusunu ana düşünce etrafında detaylandırdığı konuşmasında kural uygulayabilme",
  "tema2-tde3-4": "Konuşmasının içeriğinde kullandığı unsurların konuşmasına olan etkisini yansıtabilme",
  "tema2-tde4-4": "Yazısına yönelik değerlendirmelerini konu ve diğer yazma unsurları bağlamında yansıtabilme",
  "tema3-tde3-4": "Edebî metinlerdeki yapısal inceliklerin konuşmaya etkisine yönelik değerlendirmelerini yansıtabilme",
  "tema3-tde4-4": "Yapısını incelikle ördüğü yazısına yönelik değerlendirmelerini yansıtabilme",
  "tema4-tde1-4": "“Dilin Zenginliği” temasında ele alınan metinlere yönelik değerlendirmelerini yansıtabilme",
  "tema4-tde2-4": "“Dilin Zenginliği” temasında ele alınan metinlere yönelik değerlendirmelerini yansıtabilme",
  "tema4-tde3-4": "Kullandığı dil özelliklerinin konuşmasına etkisine yönelik değerlendirmelerini yansıtabilme",
  "tema4-tde4-4": "Yazısına yönelik değerlendirmelerini üslup ve diğer yazma unsurları bağlamında yansıtabilme"
};
for (const [id, title] of Object.entries(revisedTitles)) {
  assert.equal(outcomes.find((outcome) => outcome.id === id).title, title);
}

for (const outcome of outcomes) {
  assert.ok(outcome.id && outcome.theme && outcome.code && outcome.title && outcome.skill);
  const componentCodes = (outcome.processComponents || []).map((component) => component.code);
  assert.equal(new Set(componentCodes).size, componentCodes.length, `${outcome.id} süreç bileşeni kodları yinelenmemeli`);
}

console.log("tde9-curriculum-data.test.js: all assertions passed");
