import quantSet1 from "./quant-set-1.js";
import quantSet2 from "./quant-set-2.js";
import reasonSet1 from "./reason-set-1.js";
import reasonSet2 from "./reason-set-2.js";
import englishSet1 from "./english-set-1.js";
import gaSet1 from "./ga-set-1.js";

export const SECTION_CATALOG = [
  {
    id: "Quant",
    title: "Quantitative Aptitude",
    subtitle: "Arithmetic, Algebra, Geometry, Trigonometry, Mensuration & DI",
    sets: [
      { id: "quant-set-1", label: "Set 1", questions: quantSet1 },
      { id: "quant-set-2", label: "Set 2", questions: quantSet2 }
    ]
  },
  {
    id: "Reasoning",
    title: "General Intelligence & Reasoning",
    subtitle: "Series, Coding-Decoding, Analogy, Syllogism, Seating & Logic",
    sets: [
      { id: "reason-set-1", label: "Set 1", questions: reasonSet1 },
      { id: "reason-set-2", label: "Set 2", questions: reasonSet2 }
    ]
  },
  {
    id: "English",
    title: "English Comprehension",
    subtitle: "Idioms, OWS, Synonyms/Antonyms, Grammar Errors, Voice & Narration",
    sets: [{ id: "english-set-1", label: "Set 1", questions: englishSet1 }]
  },
  {
    id: "General Awareness",
    title: "General Awareness",
    subtitle: "Polity, History, Geography, Economy, Science, Static GK & Culture",
    sets: [{ id: "ga-set-1", label: "Set 1", questions: gaSet1 }]
  }
];
