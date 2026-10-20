export const has = (role: string, ...allowed: string[]) => allowed.includes(role);
export const canEnter = (r: string) => has(r, "content_admin", "rights_admin", "super_admin");
export const canCatalog = (r: string) => has(r, "content_admin", "super_admin");
export const canRights = (r: string) => has(r, "rights_admin", "content_admin", "super_admin");
export const canApproveRights = (r: string) => has(r, "rights_admin", "super_admin");
export const isSuper = (r: string) => r === "super_admin";

export function pagesFor(role: string): string[] {
  const p: string[] = [];
  if (canCatalog(role)) p.push("overview", "titles", "imports");
  if (canRights(role)) p.push("rights");
  if (isSuper(role)) p.push("users", "audit");
  return p;
}
