// Real vendor logos: simple-icons CDN; Microsoft is not in simple-icons,
// so its four-squares mark is inlined as a data URI.
const MICROSOFT_LOGO =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 23 23"><rect x="1" y="1" width="10" height="10" fill="%23F25022"/><rect x="12" y="1" width="10" height="10" fill="%237FBA00"/><rect x="1" y="12" width="10" height="10" fill="%2300A4EF"/><rect x="12" y="12" width="10" height="10" fill="%23FFB900"/></svg>'

export const VENDOR_LOGOS = {
  Meta: 'https://cdn.simpleicons.org/meta/0866FF',
  Alibaba: 'https://cdn.simpleicons.org/alibabacloud/FF6A00',
  Google: 'https://cdn.simpleicons.org/google',
  'Mistral AI': 'https://cdn.simpleicons.org/mistralai/FA520F',
  Microsoft: MICROSOFT_LOGO,
  Ollama: 'https://cdn.simpleicons.org/ollama/8a8f98',
}

export function logoFor(model) {
  return VENDOR_LOGOS[model.vendor] ?? VENDOR_LOGOS.Ollama
}
