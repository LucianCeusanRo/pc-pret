// Public client config. The Supabase anon key is designed to be public (it only works
// together with Row Level Security policies, see supabase/schema.sql). Leave empty to
// run the site without accounts. In CI these are filled from GitHub repository variables.
window.PCP_CONFIG = {
  SUPABASE_URL: "",
  SUPABASE_ANON_KEY: ""
};
