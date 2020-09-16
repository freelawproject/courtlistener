export interface Tag {
  id: number;
  name: string;
  title: string;
  date_created: string;
  published: boolean;
  dockets: number[];
  view_count: number;
  assocId?: number;
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
  id?: number;
  name?: string;
  editUrl?: string;
}
