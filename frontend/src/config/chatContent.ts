type WeightedItem = {
  text: string;
  weight: number;
};

export const chatContentConfig = {
  welcomeTexts: [
    { text: "Shall we talk under the moonlight?", weight: 10 },
    { text: "The cursor blinks. So does possibility.", weight: 10 },
    { text: "Every great idea starts with a question.", weight: 10 },
    { text: "What's on your mind tonight?", weight: 10 },
    { text: "Think out loud. I'm listening.", weight: 10 },
    { text: "Let's make something useful today.", weight: 10 },
    { text: "Ask anything. Really, anything.", weight: 10 },
    { text: "Your work, amplified.", weight: 10 },
    { text: "Go ahead, ask the dumb question.", weight: 10 },
    { text: "Where else are you gonna find a pro like me?", weight: 10 },
  ],
  completionNotes: [
    { text: "Done! You got more questions?", weight: 10 },
    { text: "Text generation completed", weight: 10 },
  ],
} as const;

function pickWeightedItem<T extends { weight: number }>(items: readonly T[]): T {
  const totalWeight = items.reduce((sum, item) => sum + item.weight, 0);
  const randomValue = Math.random() * totalWeight;

  let cumulativeWeight = 0;
  for (const item of items) {
    cumulativeWeight += item.weight;
    if (randomValue <= cumulativeWeight) {
      return item;
    }
  }

  // fallback for floating point errors; won't be here normally
  return items[items.length - 1];
}

export function getRandomWelcomeText(): string {
  return pickWeightedItem(chatContentConfig.welcomeTexts).text;
}

export function getRandomCompletionNote(): string {
  return pickWeightedItem(chatContentConfig.completionNotes).text;
}