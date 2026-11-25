// The browser only talks to its own origin; the web server proxies these paths
// to the gateway so session cookies stay first-party (spec 0041).
export const SHIELD_API_PREFIX = '/api/v1'
