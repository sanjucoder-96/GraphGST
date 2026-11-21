import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './Button.module.css';

export type ButtonVariant = 'default' | 'primary' | 'signal' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconOnly?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'default',
  size = 'md',
  iconOnly = false,
  className,
  children,
  ...rest
}: Props) {
  const cls = [
    styles.btn,
    variant === 'primary' ? styles.primary : '',
    variant === 'signal'  ? styles.signal  : '',
    variant === 'ghost'   ? styles.ghost   : '',
    size === 'sm' ? styles.sm : '',
    size === 'lg' ? styles.lg : '',
    iconOnly ? styles.icon : '',
    className ?? ''
  ].filter(Boolean).join(' ');
  return (
    <button className={cls} {...rest}>{children}</button>
  );
}
