export interface Tag {
  id: number;
  name: string;
  date_created: string;
  published: boolean;
  dockets: number[];
  view_count: number;
  assocId?: number;
  description: string;
}
export interface Association {
  id: number;
  tag: number;
  docket: number;
}
export interface ApiResult<T> {
  count: number;
  next: string;
  previous: string;
  results: T[];
}

export interface UserState {
  userId?: number;
  userName?: string;
  editUrl?: string;
  isPageOwner?: boolean;
  docket?: number;
}
