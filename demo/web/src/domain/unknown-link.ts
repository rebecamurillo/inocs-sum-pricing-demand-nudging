/** The instance as the card names it: its name when it exists, else the id the link writes. */
export function instanceLabel(name: string | null, instanceId: string): string {
  return name ?? instanceId;
}

export function missingInstanceVersionLabel(version: number): string {
  return `v${String(version)}`;
}

export function missingPricingVersionLabel(letter: string): string {
  return `Version ${letter}`;
}

export function nothingAtThisLink(instance: string, missing: string): string {
  return `Nothing at this link: ${instance} has no ${missing}. It may have been deleted.`;
}
