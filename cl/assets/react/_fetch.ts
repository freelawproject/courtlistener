import Cookies from 'js-cookie';

interface FetchOptions {
  method?: 'GET' | 'POST' | 'DELETE' | 'PUT' | 'PATCH' | 'OPTIONS';
  headers?: { [key: string]: any };
  body?: { [key: string]: any } | string;
}

export async function appFetch<T>(url: string, options?: FetchOptions): Promise<T | boolean> {
  const csrfTokenHeader = {
    'Content-Type': 'application/json',
    'X-CSRFToken': Cookies.get('csrftoken'),
  };

  const mergedOptions: FetchOptions = {
    method: options?.method || 'GET',
    headers: options?.headers ? { ...csrfTokenHeader, ...options.headers } : csrfTokenHeader,
  };
  if (options?.body) {
    mergedOptions.body = JSON.stringify(options.body);
  }

  return fetch(url, mergedOptions as RequestInit).then((response) => {
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    if (options?.method === 'DELETE') return new Promise((resolve) => resolve(true));
    return response.json() as Promise<T>;
  });
}
