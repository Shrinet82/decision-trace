/**
 * Drop-in replacements for the react-router pieces that take app paths. Pages keep writing
 * `/decisions/DEC-11`; these add `/app` or `/app/o/<org>` in front, and `useLocation` hands back
 * the pathname without it.
 */
import React from 'react';
import {
  Link as RouterLink,
  NavLink as RouterNavLink,
  Navigate as RouterNavigate,
  useLocation as useRouterLocation,
  useNavigate as useRouterNavigate,
  type LinkProps,
  type NavLinkProps,
  type NavigateProps,
  type NavigateOptions,
} from 'react-router-dom';
import { withBase, stripBase } from './org/orgState';
import { useOrgSlug } from './org/OrgContext';

export { Outlet, useParams, useSearchParams } from 'react-router-dom';

const prefixed = (to: LinkProps['to'], slug: string | null): LinkProps['to'] =>
  typeof to === 'string' ? withBase(to, slug) : to;

export const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link({ to, ...rest }, ref) {
  const slug = useOrgSlug();
  return <RouterLink ref={ref} to={prefixed(to, slug)} {...rest} />;
});

export const NavLink = React.forwardRef<HTMLAnchorElement, NavLinkProps>(function NavLink(
  { to, ...rest },
  ref
) {
  const slug = useOrgSlug();
  return <RouterNavLink ref={ref} to={prefixed(to, slug)} {...rest} />;
});

export const Navigate: React.FC<NavigateProps> = ({ to, ...rest }) => {
  const slug = useOrgSlug();
  return <RouterNavigate to={prefixed(to, slug)} {...rest} />;
};

export function useNavigate() {
  const navigate = useRouterNavigate();
  const slug = useOrgSlug();
  return React.useCallback(
    (to: string | number, options?: NavigateOptions) => {
      if (typeof to === 'number') navigate(to);
      else navigate(withBase(to, slug), options);
    },
    [navigate, slug]
  );
}

export function useLocation() {
  const location = useRouterLocation();
  return React.useMemo(() => ({ ...location, pathname: stripBase(location.pathname) }), [location]);
}
