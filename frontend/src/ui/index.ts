// src/ui: the primitives library (UI-UX-PLAYBOOK section 4, W4-02).
// Styles live in src/styles/ui.css (imported globally from index.css).
// StatusBadge is built separately (src/ui/StatusBadge.tsx + src/design/status.ts).
export { Button, ButtonLink, IconButton } from './Button';
export type { ButtonProps, ButtonLinkProps, ButtonSize, ButtonVariant, IconButtonProps } from './Button';
export { Card } from './Card';
export type { CardProps, CardTone } from './Card';
export { DataTable } from './DataTable';
export type { Column, DataTableProps, SortDirection, SortState } from './DataTable';
export { DeadlineChip, describeDeadline } from './DeadlineChip';
export type { DeadlineChipProps, DeadlineDescription, DeadlineTone } from './DeadlineChip';
export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { Field } from './Field';
export type { FieldInputMode, FieldProps } from './Field';
export { Icon, ICON_NAMES } from './Icon';
export type { IconName } from './Icon';
export { ListCard } from './ListCard';
export type { ListCardProps } from './ListCard';
export { Dialog, Modal, Sheet } from './Modal';
export type { DialogProps, ModalProps, ModalSize } from './Modal';
export { PageHeader } from './PageHeader';
export type { PageHeaderProps } from './PageHeader';
export { PageState } from './PageState';
export type { PageStateProps, PageStateValue } from './PageState';
export { PromptDialog, usePromptDialog } from './PromptDialog';
export type { PromptDialogProps, PromptOptions } from './PromptDialog';
export { TabBar, Tabs, useTabParam } from './Tabs';
export type { TabBarItem, TabBarProps, TabItem, TabsProps } from './Tabs';
