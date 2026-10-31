// Public interview preview: show the short debug test on the deployed site too.
// Set VITE_DEBUG_MODE=false before building to turn these UI controls off.
// This flag never disables authentication or changes verification requirements.
export const DEBUG_MODE = import.meta.env.VITE_DEBUG_MODE !== "false"
