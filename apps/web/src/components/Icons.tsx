/**
 * The interface's line icons: one 24px grid, one stroke, round ends.
 *
 * Every icon is decorative. It always sits beside a word that carries its
 * meaning, so it is hidden from assistive technology and never the only name
 * a control has.
 */
import type { ReactNode } from "react";

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

type Props = { size?: number };

export const LibraryIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M4 19.5V5.5A1.5 1.5 0 0 1 5.5 4H9v16H5.5A1.5 1.5 0 0 1 4 18.5" />
    <path d="M9 4h4v16H9" />
    <path d="m14.5 5.2 3.4-.9a1 1 0 0 1 1.2.7l3 11.6a1 1 0 0 1-.7 1.2l-3.4.9" />
  </Icon>
);

export const BookmarkIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M7 3.5h10a1 1 0 0 1 1 1V21l-6-4-6 4V4.5a1 1 0 0 1 1-1Z" />
  </Icon>
);

export const ClassesIcon = ({ size }: Props) => (
  <Icon size={size}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3 19.5c.7-3.2 3.1-5 6-5s5.3 1.8 6 5" />
    <path d="M15.5 4.9a3.2 3.2 0 0 1 0 6.2" />
    <path d="M17.8 14.6c1.6.6 2.8 2.2 3.2 4.9" />
  </Icon>
);

export const ProgressIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M4 20V10" />
    <path d="M10 20V4" />
    <path d="M16 20v-7" />
    <path d="M21 20H3" />
  </Icon>
);

export const OfflineIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M12 4v11" />
    <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
    <path d="M4.5 19.5h15" />
  </Icon>
);

export const HeadphonesIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M4 15v-3a8 8 0 0 1 16 0v3" />
    <rect x="3.5" y="14" width="4.5" height="6.5" rx="1.6" />
    <rect x="16" y="14" width="4.5" height="6.5" rx="1.6" />
  </Icon>
);

export const AnswerIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M20 12.5a7.5 7.5 0 0 1-11 6.6L4 20.5l1.4-4.6A7.5 7.5 0 1 1 20 12.5Z" />
    <path d="M9 11h6M9 14.5h3.5" />
  </Icon>
);

export const PractiseIcon = ({ size }: Props) => (
  <Icon size={size}>
    <rect x="4" y="3.5" width="16" height="17" rx="2.5" />
    <path d="m8 10 2 2 4-4" />
    <path d="M8 16h8" />
  </Icon>
);

export const TrackIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M3.5 17.5 9 12l3.5 3.5L20.5 7.5" />
    <path d="M15.5 7.5h5v5" />
  </Icon>
);

export const ArrowRightIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M5 12h14" />
    <path d="m13 6 6 6-6 6" />
  </Icon>
);

export const CheckIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Icon>
);

export const KeyboardIcon = ({ size }: Props) => (
  <Icon size={size}>
    <rect x="2.5" y="6" width="19" height="12" rx="2.5" />
    <path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M8 14h8" />
  </Icon>
);

export const ShieldIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M12 3.5 19 6v5.5c0 4.4-3 7.7-7 9-4-1.3-7-4.6-7-9V6l7-2.5Z" />
    <path d="m9 12 2.2 2.2L15.5 10" />
  </Icon>
);

export const SignOutIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M14 4.5h3.5A1.5 1.5 0 0 1 19 6v12a1.5 1.5 0 0 1-1.5 1.5H14" />
    <path d="M10 8 6 12l4 4" />
    <path d="M6 12h9" />
  </Icon>
);

export const PlayIcon = ({ size }: Props) => (
  <Icon size={size}>
    <path d="M8 5.5v13l10.5-6.5L8 5.5Z" fill="currentColor" />
  </Icon>
);
