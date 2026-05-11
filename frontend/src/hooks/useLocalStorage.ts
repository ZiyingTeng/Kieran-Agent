/**
 * useLocalStorage - Custom hook for localStorage with Zustand-like API
 */

import { useCallback } from 'react';

interface UseLocalStorageReturn<T> {
  value: T;
  setValue: (value: T | ((prev: T) => T)) => void;
  removeValue: () => void;
}

export function useLocalStorage<T>(
  key: string,
  initialValue: T
): UseLocalStorageReturn<T> {
  const getValue = useCallback((): T => {
    if (typeof window === 'undefined') return initialValue;

    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.error(`Error reading localStorage key "${key}":`, error);
      return initialValue;
    }
  }, [key, initialValue]);

  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      try {
        const valueToStore = value instanceof Function ? value(getValue()) : value;
        window.localStorage.setItem(key, JSON.stringify(valueToStore));
        // Trigger storage event for cross-tab sync
        window.dispatchEvent(new Event('local-storage'));
      } catch (error) {
        console.error(`Error setting localStorage key "${key}":`, error);
      }
    },
    [key, getValue]
  );

  const removeValue = useCallback(() => {
    try {
      window.localStorage.removeItem(key);
      window.dispatchEvent(new Event('local-storage'));
    } catch (error) {
      console.error(`Error removing localStorage key "${key}":`, error);
    }
  }, [key]);

  return {
    value: getValue(),
    setValue,
    removeValue,
  };
}
