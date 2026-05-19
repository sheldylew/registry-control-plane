export function authenticatedLandingPath(user) {
  return user?.is_admin ? "/admin" : "/repos";
}
