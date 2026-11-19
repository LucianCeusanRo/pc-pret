// Courier adapters.
//
// Today every courier uses the "manual" flow: the sell request is saved and we
// contact the seller to arrange pickup. No courier API is called, because real
// pickup booking needs a business contract and API keys we don't have yet.
//
// To plug in a real API later, give a courier a `bookPickup(request)` that runs
// on a SERVER (never put courier API keys in this browser code), e.g. a Supabase
// Edge Function or a Vercel Function, and returns { ok, awb, trackingUrl }.
// See README "Courier adapters".

const manual = {
  mode: "manual",
  async bookPickup(_request) {
    return { ok: true, mode: "manual", awb: null, trackingUrl: null };
  },
};

window.COURIERS = {
  RO: [
    { id: "fan", name: "Fan Courier", ...manual },
    { id: "sameday", name: "Sameday", ...manual },
    { id: "cargus", name: "Cargus", ...manual },
  ],
  BG: [
    { id: "speedy", name: "Speedy", ...manual },
    { id: "econt", name: "Econt", ...manual },
  ],
  HU: [
    { id: "gls", name: "GLS", ...manual },
    { id: "mpl", name: "MPL (Magyar Posta)", ...manual },
  ],
};
