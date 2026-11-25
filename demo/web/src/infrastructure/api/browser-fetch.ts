/** The browser's fetch behind a wrapper, so that it is not called on the gateway that holds it. */
export const browserFetch: typeof fetch = (input, init) => fetch(input, init);
